"""Pure reducer for the enemy side: apply(state, action) -> state. No Streamlit imports."""
from __future__ import annotations

import copy
from collections.abc import Callable

from . import events as ev
from .catalog import Catalog
from .combat import damage_pipeline, prevention, start_of_turn_damage
from .events import Action
from .setup import GameSetup
from .state import COUNT_TOKENS, EnemyTitan, FightResult, GameState, LogEntry, Reveal

FIGHT_END_REASONS = ("enemy_defeated", "player_defeated", "both_defeated", "enemy_returned", "player_returned")


# ---------------------------------------------------------------- construction

def _enemy(catalog: Catalog, card_id: str) -> EnemyTitan:
    c = catalog.titans[card_id]
    return EnemyTitan(
        card_id=c.id, name=c.name, max_life=c.max_life, base_speed=c.speed,
        base_armor=c.armor, team_power=c.team_power, legendary_id=c.legendary_id,
    )


def initial_state(setup: GameSetup, catalog: Catalog) -> GameState:
    n = setup.player_titan_count()
    return GameState(
        seed=setup.seed, player_titans_total=n, player_titans_left=n,
        deck=[_enemy(catalog, cid) for cid in setup.enemy_titans],
        upgrade_hand=list(setup.enemy_upgrades), total=len(setup.enemy_titans),
    )


def reduce(initial: GameState, actions: list[Action]) -> GameState:
    state = copy.deepcopy(initial)
    for a in actions:
        apply_inplace(state, a)
    return state


def apply(state: GameState, action: Action) -> GameState:
    new = copy.deepcopy(state)
    apply_inplace(new, action)
    return new


def apply_inplace(state: GameState, action: Action) -> None:
    state.hints = []
    state.last_reveals = []
    state.event_count += 1
    handler = HANDLERS.get(action.kind)
    if handler is None:
        _log(state, f"Unknown action '{action.kind}' ignored.")
        return
    handler(state, **action.args)
    for h in state.hints:
        state.log.append(LogEntry(state.event_count, h, "hint"))


# --------------------------------------------------------------------- helpers

def _log(state: GameState, text: str) -> None:
    state.log.append(LogEntry(state.event_count, text))


def _hint(state: GameState, text: str) -> None:
    state.hints.append(text)


def _reveal_to_bench(state: GameState) -> None:
    if not state.deck:
        return
    t = state.deck.pop(0)
    if t.legendary_id:
        t.legendary_upgrade = t.legendary_id
    state.bench.append(t)
    state.last_reveals.append(Reveal("titan", t.card_id, "bench"))
    _log(state, f"{t.name} is revealed on the enemy bench.")


def _enter_arena(state: GameState, role: str) -> None:
    if not state.bench:
        _reveal_to_bench(state)
    if not state.bench:
        return
    t = state.bench.pop(0)
    t.life = t.max_life
    t.charged = False
    state.arena = t
    state.enemy_role = role  # type: ignore[assignment]
    # A Titan revealed to the bench and moved into the arena at once is reported only once.
    state.last_reveals = [r for r in state.last_reveals if not (r.kind == "titan" and r.card_id == t.card_id)]
    state.last_reveals.append(Reveal("titan", t.card_id, "arena"))
    _log(state, f"{t.name} enters the arena as enemy {role.capitalize()}.")
    if not state.bench:
        _reveal_to_bench(state)


def _reveal_upgrades(state: GameState) -> None:
    if not state.upgrade_hand:
        state.new_upgrades = []
        return
    if state.enemy_remaining() == 1:
        revealed = list(state.upgrade_hand)
        state.upgrade_hand.clear()
        if len(revealed) > 1:
            _hint(state, "Final fight: all remaining enemy Upgrades are revealed.")
    else:
        revealed = [state.upgrade_hand.pop(0)]
    state.active_upgrades += revealed
    state.new_upgrades = revealed
    for up in revealed:
        state.last_reveals.append(Reveal("upgrade", up))
    _log(state, f"{len(revealed)} enemy Upgrade(s) revealed. They stay active for the rest of the game.")


def _reset_turn(state: GameState) -> None:
    state.active_side = None
    state.turn_started = False


# ----------------------------------------------------------------- fight flow

def begin_game(state: GameState) -> None:
    if state.phase != "start":
        return
    _log(state, "Game begins.")
    _enter_arena(state, "champion")
    _reveal_upgrades(state)
    state.phase = "fight_start"


def set_starter(state: GameState, side: str) -> None:
    if state.phase != "fight_start" or state.arena is None or side not in ("enemy", "players"):
        return
    state.phase = "combat"
    state.active_side = side  # type: ignore[assignment]
    state.turn_started = side == "players"
    _log(state, f"Combat begins. {'The enemy' if side == 'enemy' else 'The players'} start.")


def start_turn(state: GameState) -> None:
    t = state.arena
    if state.phase != "combat" or state.active_side != "enemy" or state.turn_started or t is None:
        return
    state.turn_no += 1
    st = t.statuses
    dmg = start_of_turn_damage(st.poison, st.fire)
    if dmg:
        parts = [f"Poison ({st.poison})"] * bool(st.poison) + [f"Fire ({st.fire})"] * bool(st.fire)
        t.life = max((t.life or 0) - dmg, 0)
        _log(state, f"{t.name} takes {dmg} damage from {' and '.join(parts)}.")
        _hint(state, "Poison and Fire damage ignore Armor, Dodge, and Minion.")
        if st.fire:
            st.fire += 1
            _hint(state, f"Fire grows to {st.fire}.")
    else:
        _log(state, f"The enemy's turn starts ({t.name}).")
    if (t.life or 0) <= 0:
        _end_fight(state, "enemy_defeated")
        return
    state.turn_started = True


def end_turn(state: GameState) -> None:
    if state.phase != "combat" or state.active_side is None:
        return
    ending = state.active_side
    _log(state, "The enemy's turn ends." if ending == "enemy" else "The players' turn ends.")
    state.active_side = "players" if ending == "enemy" else "enemy"
    state.turn_started = state.active_side == "players"
    if state.active_side == "players":
        state.turn_no += 1


# --------------------------------------------------------------------- damage

def damage(state: GameState, base: int = 0, bonus: int = 0, cancel: bool = False, replacement: int | None = None) -> None:
    t = state.arena
    if t is None or not state.in_fight():
        _log(state, "Damage ignored: no enemy in the arena.")
        return
    calc = damage_pipeline(base, 0, bonus, cancel, t.armor, replacement)
    life = t.life or 0
    final, used = prevention(calc.final, life, t.statuses.dodge, t.statuses.minion)
    steps = [f"base {base}"]
    if bonus:
        steps.append(f"{bonus:+d} bonus")
    if cancel:
        steps.append("canceled")
    if calc.armor_reduced:
        steps.append(f"-{calc.armor_reduced} Armor")
        _hint(state, f"Armor {t.armor} reduced the damage from {calc.after_cancel} to {calc.after_armor}.")
    if replacement is not None:
        steps.append(f"replaced by {replacement}")
    if used == "dodge":
        t.statuses.dodge -= 1
        _hint(state, f"Dodge absorbed the damage. {t.name} loses 1 Dodge token.")
    elif used == "minion":
        t.statuses.minion -= 1
        _hint(state, f"Minion prevented the defeat. {t.name} loses 1 Minion token.")
    t.life = max(life - final, 0)
    _log(state, f"{t.name} takes {final} damage ({', '.join(steps)}).")
    if t.life <= 0:
        _end_fight(state, "enemy_defeated")


def heal(state: GameState, amount: int) -> None:
    t = state.arena
    if t is None or t.life is None:
        return
    before = t.life
    t.life = min(t.max_life, t.life + max(amount, 0))
    _log(state, f"{t.name} heals {t.life - before} Life.")


def life_adjust(state: GameState, delta: int) -> None:
    t = state.arena
    if t is None or t.life is None or not state.in_fight():
        return
    t.life = max(0, min(t.max_life, t.life + delta))
    _log(state, f"Manual: {t.name} Life {delta:+d} (now {t.life}).")
    if t.life <= 0:
        _end_fight(state, "enemy_defeated")


# --------------------------------------------------------------------- tokens

def token(state: GameState, target: str, token: str, delta: int) -> None:
    t = state.find(target)
    if t is None:
        return
    st = t.statuses
    if token in ("blessed", "cursed"):
        if delta > 0:
            if st.blessed_cursed == "none":
                st.blessed_cursed = token  # type: ignore[assignment]
            elif st.blessed_cursed == token:
                _hint(state, f"{t.name} already has {token.capitalize()}; it keeps the token it has.")
            else:
                _hint(state, f"{t.name} had {st.blessed_cursed.capitalize()}; the opposite token removes it instead.")
                st.blessed_cursed = "none"
        elif st.blessed_cursed == token:
            st.blessed_cursed = "none"
    elif token in COUNT_TOKENS:
        before = getattr(st, token)
        setattr(st, token, max(0, before + delta))
    else:
        return
    _log(state, f"{t.name}: {token} {delta:+d}.")


def flag(state: GameState, target: str, flag: str, value: bool) -> None:
    t = state.find(target)
    if t is None or flag not in ("charged", "ultimate_form"):
        return
    setattr(t, flag, bool(value))
    _log(state, f"{t.name}: {flag.replace('_', ' ')} {'on' if value else 'off'}.")


def speed(state: GameState, value: int | None) -> None:
    t = state.arena
    if t is None:
        return
    t.speed_override = value
    _log(state, f"{t.name} Speed is now {t.speed}.")


# ------------------------------------------------------------ fight endings

def _end_fight(state: GameState, reason: str) -> None:
    t = state.arena
    if t is None or reason not in FIGHT_END_REASONS:
        return
    winner = {"enemy_defeated": "players", "enemy_returned": "players", "player_defeated": "enemy",
              "player_returned": "enemy"}.get(reason)
    result = FightResult(reason=reason, winner=winner, enemy_id=t.card_id)  # type: ignore[arg-type]
    if reason in ("enemy_defeated", "both_defeated"):
        result.legendary = t.legendary_upgrade
        state.defeated.append(t.card_id)
        state.arena = None
        state.enemy_role = None
        _log(state, f"{t.name} is defeated.")
    elif reason == "enemy_returned":
        t.life = None
        t.charged = False
        t.statuses.fire = 0
        state.bench.insert(0, t)
        state.arena = None
        state.enemy_role = None
        _hint(state, "The enemy Titan returned to its bench. It fights next, and no new enemy Upgrade is revealed.")
        _log(state, f"{t.name} returns to the enemy bench and heals to full Life.")
    else:
        t.statuses.fire = 0
        t.charged = False
        state.enemy_role = "champion"
        _log(state, f"{t.name} wins the fight and stays as enemy Champion.")
    if reason in ("player_defeated", "both_defeated"):
        state.player_titans_left = max(state.player_titans_left - 1, 0)
        _log(state, f"A player Titan is defeated ({state.player_titans_left} left).")
    if reason == "both_defeated":
        _hint(state, "Both Titans were defeated at the same time; nobody gets the victory reward.")
    state.result = result
    _reset_turn(state)
    if state.player_titans_left == 0:
        state.phase = "defeat"
        _log(state, "All player Titans are defeated. The enemy wins.")
    elif state.enemy_remaining() == 0:
        state.phase = "victory"
        _log(state, "Every enemy Titan is defeated. The players win!")
    else:
        state.phase = "cleanup"


def fight_end(state: GameState, reason: str) -> None:
    if not state.in_fight():
        return
    _end_fight(state, reason)


def swap(state: GameState, with_id: str) -> None:
    t = state.arena
    incoming = next((b for b in state.bench if b.card_id == with_id), None)
    if t is None or incoming is None or not state.in_fight():
        return
    idx = state.bench.index(incoming)
    t.life = None
    t.charged = False
    t.statuses.fire = 0
    state.bench[idx] = t
    incoming.life = incoming.max_life
    incoming.charged = False
    state.arena = incoming
    _log(state, f"{t.name} swaps with {incoming.name}; the fight continues.")
    _hint(state, "Swapping is not a new fight, so Start of Fight abilities do not trigger again.")


def advance_fight(state: GameState) -> None:
    if state.phase != "cleanup" or state.result is None:
        return
    result = state.result
    if result.reason != "enemy_returned":
        _reveal_upgrades(state)
    else:
        state.new_upgrades = []
    if state.arena is None:
        # A player Titan holds the arena unless both fighters fell.
        role = "champion" if result.reason == "both_defeated" else "challenger"
        _enter_arena(state, role)
    elif not state.bench:
        _reveal_to_bench(state)
    state.phase = "fight_start"
    state.fight_no += 1
    state.result = None
    _reset_turn(state)


def add_enemy_upgrade(state: GameState, card_id: str) -> None:
    state.upgrade_hand.append(card_id)
    _log(state, "A face-down Upgrade is added to the enemy hand.")


def note(state: GameState, text: str) -> None:
    _log(state, f"Note: {text}")


HANDLERS: dict[str, Callable[..., None]] = {
    ev.BEGIN_GAME: begin_game,
    ev.SET_STARTER: set_starter,
    ev.START_TURN: start_turn,
    ev.END_TURN: end_turn,
    ev.DAMAGE: damage,
    ev.HEAL: heal,
    ev.LIFE_ADJUST: life_adjust,
    ev.TOKEN: token,
    ev.FLAG: flag,
    ev.SPEED: speed,
    ev.FIGHT_END: fight_end,
    ev.SWAP: swap,
    ev.ADD_ENEMY_UPGRADE: add_enemy_upgrade,
    ev.NOTE: note,
    ev.ADVANCE_FIGHT: advance_fight,
}
