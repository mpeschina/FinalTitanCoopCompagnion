"""Cue pipeline: turns one engine action and the state change it caused into presentation cues.

Pure Python, no Streamlit imports. The engine stays untouched; cues are derived from (action, before, after).
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from finaltitan import events as ev
from finaltitan.combat import damage_pipeline
from finaltitan.engine import apply
from finaltitan.events import Action
from finaltitan.state import COUNT_TOKENS, EnemyTitan, GameState

DATA_FILE = Path(__file__).resolve().parent / "data" / "fx.yaml"
KO_STYLES = ("slash", "dissolve", "shatter")
KO_STYLE_OPTIONS = ["Auto", "Random", "Slash", "Dissolve", "Shatter"]
INTENSITIES = ["Off", "Low", "Full"]
CINEMATICS = ["Always", "Key moments only", "Off"]
SPEEDS = [0.5, 1.0, 1.5, 2.0]
REDUCED_MOTION = ["System", "On", "Off"]
# Cinematics that still play with the "Key moments only" setting.
KEY_MOMENTS = frozenset({"reveal_arena", "ultimate", "ko", "player_lost", "final_fight", "victory", "defeat"})


@lru_cache(maxsize=1)
def config() -> dict[str, Any]:
    with open(DATA_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass(frozen=True)
class Cue:
    id: str  # "act-142-0": action number + position, unique and stable
    kind: str
    target: str | None = None  # "card-<id>", "screen", "titans-left", ...
    params: dict[str, Any] = field(default_factory=dict)
    blocking: bool = False
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FxSettings:
    intensity: str = "Full"
    cinematics: str = "Key moments only"
    speed: float = 1.0
    sound: bool = False
    volume: float = 0.6
    taunts: bool = True
    ko_style: str = "Auto"
    idle: bool = True
    reduced_motion: str = "System"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def card_target(card_id: str) -> str:
    return f"card-{card_id}"


def damage_word(amount: int) -> str | None:
    for minimum, word in config()["words"]["damage"]:
        if amount >= minimum:
            return word
    return None


def tier(amount: int) -> int:
    word = damage_word(amount)
    return config()["tiers"].get(word, 0) if word else 0


def taunt(kind: str, n: int) -> str:
    options = config()["taunts"].get(kind) or []
    return options[n % len(options)] if options else ""


def _word(key: str) -> str:
    return config()["words"][key]


def _life_after(t: EnemyTitan, after: GameState) -> int:
    """Life of an enemy that was in the arena before the action; 0 if it was defeated."""
    now = after.arena if after.arena and after.arena.card_id == t.card_id else None
    if now is not None:
        return now.life or 0
    return 0 if t.card_id in after.defeated else (t.life or 0)


def is_ultimate(action: Action, before: GameState) -> bool:
    """Convention: switching Charge off during the enemy's turn means the Ultimate fired."""
    t = before.find(action.args.get("target", ""))
    return (
        action.kind == ev.FLAG and action.args.get("flag") == "charged" and not action.args.get("value")
        and t is not None and t.charged and before.phase == "combat" and before.active_side == "enemy"
    )


def ko_params(action: Action, before: GameState, after: GameState, setting: str = "Auto") -> dict[str, Any]:
    """Destroy style for a defeated enemy (§3.5). Deterministic for a given action."""
    t = before.arena
    assert t is not None
    last = after.enemy_remaining() == 0
    params: dict[str, Any] = {"slowmo": last, "color": "ash", "cuts": 1}
    style = setting.lower()
    if style == "random":
        style = random.Random(after.event_count).choice(KO_STYLES)
    if style in KO_STYLES:
        params["style"] = style
        if style == "dissolve":
            params["color"] = "fire" if t.statuses.fire else "poison" if t.statuses.poison else "ash"
        params["cuts"] = 2
        return params
    blow = None
    if action.kind == ev.DAMAGE:
        a = action.args
        blow = damage_pipeline(int(a.get("base", 0)), 0, int(a.get("bonus", 0)), bool(a.get("cancel", False)),
                               t.armor, a.get("replacement")).final
    elif action.kind == ev.LIFE_ADJUST:
        blow = abs(int(action.args.get("delta", 0)))
    if action.kind == ev.START_TURN and (t.statuses.fire or t.statuses.poison):
        params.update(style="dissolve", color="fire" if t.statuses.fire else "poison")
    elif last or (blow is not None and blow >= 5):
        params["style"] = "shatter"
    elif blow:
        params.update(style="slash", cuts=min(3, blow))
    else:
        params["style"] = KO_STYLES[(before.fight_no - 1) % len(KO_STYLES)]
    return params


class _Builder:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.cues: list[Cue] = []

    def add(self, kind: str, target: str | None = None, blocking: bool = False, **params: Any) -> None:
        params = {k: v for k, v in params.items() if v is not None}
        if blocking:
            params["key"] = kind in KEY_MOMENTS
        duration = int(config()["durations"].get(kind, 600))
        self.cues.append(Cue(f"{self.prefix}-{len(self.cues)}", kind, target, params, blocking, duration))


def _life_change(b: _Builder, t: EnemyTitan, life_to: int, word: str | None, n: int) -> None:
    life_from = t.life or 0
    delta = life_to - life_from
    common = {"life_from": life_from, "life_to": life_to, "max_life": t.max_life}
    if delta < 0:
        b.add("hit", card_target(t.card_id), amount=-delta, word=word, tier=max(tier(-delta), 1), **common)
        if word and -delta <= 2 and life_to > 0:
            b.add("taunt", card_target(t.card_id), text=taunt("hit_small", n))
    elif delta > 0:
        b.add("heal", card_target(t.card_id), amount=delta, **common)


def _token_cues(b: _Builder, before_t: EnemyTitan, after_t: EnemyTitan, where: str) -> None:
    target = card_target(after_t.card_id)
    for name in COUNT_TOKENS:
        old, new = getattr(before_t.statuses, name), getattr(after_t.statuses, name)
        if old != new:
            b.add("token", target, token=name, delta=new - old, value=new, where=where)
    old_bc, new_bc = before_t.statuses.blessed_cursed, after_t.statuses.blessed_cursed
    if old_bc != new_bc:
        if old_bc != "none":
            b.add("poof", target, token=old_bc, word=_word("poof"), where=where)
        if new_bc != "none":
            b.add("token", target, token=new_bc, delta=1, value=1, where=where)


def cues_for(
    action: Action,
    before: GameState,
    after: GameState,
    *,
    prefix: str | None = None,
    summary: dict[str, Any] | None = None,
    difficulty: str = "",
    ko_setting: str = "Auto",
) -> list[Cue]:
    """Cues for one action, in timeline order (§3.3)."""
    n = after.event_count
    b = _Builder(prefix or f"act-{n}")
    kind, args = action.kind, action.args
    bt = before.arena

    if kind == ev.BEGIN_GAME and before.phase == "start" and after.phase != "start":
        b.add("title", "screen", True, difficulty=difficulty or None)

    # Start-of-turn ticks, then damage and heal.
    if kind == ev.START_TURN and bt is not None and (after.turn_started or after.result) and not before.turn_started:
        target = card_target(bt.card_id)
        b.add("lunge", target, taunt=taunt("start_turn", n))
        life_to = _life_after(bt, after)
        if life_to < (bt.life or 0):
            st = bt.statuses
            b.add("tick", target, poison=st.poison, fire=st.fire, word=_word("fire" if st.fire else "poison"))
            _life_change(b, bt, life_to, None, n)
        at = after.arena
        if at is not None and at.card_id == bt.card_id:
            if at.statuses.fire > bt.statuses.fire:
                b.add("token", target, token="fire", delta=at.statuses.fire - bt.statuses.fire, value=at.statuses.fire, where="arena")
            if after.turn_started and at.statuses.action:
                b.add("combo", target, actions=1 + at.statuses.action)
    elif kind == ev.DAMAGE and bt is not None and before.in_fight():
        target = card_target(bt.card_id)
        calc = damage_pipeline(int(args.get("base", 0)), 0, int(args.get("bonus", 0)), bool(args.get("cancel", False)),
                               bt.armor, args.get("replacement"))
        if calc.armor_reduced > 0:
            b.add("armor", target, word=_word("armor"), **{"from": calc.after_cancel, "to": calc.after_armor})
        life_to = _life_after(bt, after)
        at = after.find(bt.card_id)
        if life_to < (bt.life or 0):
            _life_change(b, bt, life_to, damage_word((bt.life or 0) - life_to), n)
        elif at is not None and at.statuses.dodge < bt.statuses.dodge:
            b.add("dodge", target, word=_word("dodge"), taunt=taunt("dodge", n))
        elif at is not None and at.statuses.minion < bt.statuses.minion:
            b.add("minion", target, word=_word("minion"), taunt=taunt("minion", n))
        else:
            b.add("whiff", target, word=_word("whiff"), taunt=taunt("whiff", n))
    elif kind in (ev.HEAL, ev.LIFE_ADJUST) and bt is not None:
        _life_change(b, bt, _life_after(bt, after), None, n)

    # Token changes.
    if kind == ev.TOKEN:
        old, new = before.find(args.get("target", "")), after.find(args.get("target", ""))
        if old is not None and new is not None:
            _token_cues(b, old, new, "arena" if after.arena is new else "bench")

    # Charge, Ultimate, Ultimate Form.
    if kind == ev.FLAG:
        old, new = before.find(args.get("target", "")), after.find(args.get("target", ""))
        if old is not None and new is not None:
            target = card_target(new.card_id)
            if args.get("flag") == "charged" and old.charged != new.charged:
                if new.charged:
                    b.add("charge_on", target, word=_word("charge"))
                elif is_ultimate(action, before):
                    b.add("ultimate", target, True, word=_word("ultimate"), name=new.name, taunt=taunt("ultimate", n))
                else:
                    b.add("charge_off", target)
            elif args.get("flag") == "ultimate_form" and new.ultimate_form and not old.ultimate_form:
                b.add("ultimate_form", target)

    # Turn order.
    if kind == ev.SET_STARTER and before.phase == "fight_start" and after.phase == "combat" and after.arena:
        b.add("vs", "screen", True, name=after.arena.name, card=card_target(after.arena.card_id),
              role=after.enemy_role, word=_word("fight"), taunt=taunt("fight", n))
        b.add("turn_banner", "screen", side=after.active_side)
    if kind == ev.END_TURN and after.active_side != before.active_side and after.active_side:
        b.add("turn_banner", "screen", side=after.active_side)

    if kind == ev.SWAP and bt is not None and after.arena is not None and after.arena.card_id != bt.card_id:
        b.add("swap", card_target(after.arena.card_id), out=card_target(bt.card_id))

    # Fight end.
    if after.result is not None and before.result is None and bt is not None:
        reason = after.result.reason
        if reason in ("enemy_defeated", "both_defeated"):
            b.add("ko", card_target(bt.card_id), True, name=bt.name, word=_word("ko"),
                  defeated=len(after.defeated), total=after.total, **ko_params(action, before, after, ko_setting))
        if after.player_titans_left < before.player_titans_left:
            b.add("player_lost", "titans-left", True, left=after.player_titans_left, total=after.player_titans_total,
                  taunt=taunt("player_lost", n))
        if reason == "enemy_returned":
            b.add("retreat", card_target(bt.card_id), True, name=bt.name, word=_word("retreat"))

    # Reveals: Upgrades first, then the arena Titan, then the bench.
    ups = [r.card_id for r in after.last_reveals if r.kind == "upgrade"]
    if len(ups) > 1:
        b.add("final_fight", "screen", True, count=len(ups))
    for i, uid in enumerate(ups):
        b.add("reveal_upgrade", card_target(uid), order=i)
    bench_before = {t.card_id for t in before.bench}
    for r in after.last_reveals:
        if r.kind == "titan" and r.where == "arena":
            card = after.find(r.card_id)
            from_bench = r.card_id in bench_before
            b.add("reveal_arena", card_target(r.card_id), True, name=card.name if card else r.card_id,
                  role=after.enemy_role, **{"from": "next-enemy" if from_bench else "deck", "flip": not from_bench})
    for r in after.last_reveals:
        if r.kind == "titan" and r.where == "bench":
            b.add("reveal_bench", card_target(r.card_id), **{"from": "deck", "flip": True})

    if after.phase in ("victory", "defeat") and before.phase != after.phase:
        b.add(after.phase, "screen", True, **(summary or {}))
    return b.cues


def marks_for(cues: list[Cue], action_no: int) -> dict[str, tuple[int, Any]]:
    """Layer 2 marks: target -> (action number, value before), so CSS animations play once per action."""
    marks: dict[str, tuple[int, Any]] = {}
    for c in cues:
        p = c.params
        card_id = c.target[5:] if c.target and c.target.startswith("card-") else None
        if c.kind in ("hit", "heal") and card_id:
            marks[f"life-{card_id}"] = (action_no, round(p["life_from"] / p["max_life"], 3) if p["max_life"] else 0)
            marks[c.target] = (action_no, f"hit{p['tier']}" if c.kind == "hit" else "heal")
        elif c.kind in ("token", "poof") and card_id:
            marks[f"badge-{card_id}-{p['token']}"] = (action_no, p.get("value", 0) - p.get("delta", 0))
        elif c.kind in ("reveal_upgrade", "reveal_arena", "reveal_bench", "retreat") and c.target:
            marks[c.target] = (action_no, "arrive")
        elif c.kind == "swap" and c.target:
            marks[c.target] = (action_no, "arrive")
            marks[p["out"]] = (action_no, "arrive")
        elif c.kind in ("charge_on", "charge_off", "ultimate") and card_id:
            marks[f"charge-{card_id}"] = (action_no, c.kind)
    return marks


def game_summary(initial: GameState, actions: list[Action]) -> dict[str, Any]:
    """Totals for the victory and game-over panels."""
    state = initial
    damage = ultimates = 0
    for a in actions:
        nxt = apply(state, a)
        t = state.arena
        if t is not None and a.kind in (ev.DAMAGE, ev.START_TURN, ev.LIFE_ADJUST):
            damage += max(0, (t.life or 0) - _life_after(t, nxt))
        if is_ultimate(a, state):
            ultimates += 1
        state = nxt
    return {
        "fights": state.fight_no, "kos": len(state.defeated), "total": state.total, "ultimates": ultimates,
        "damage": damage, "titans_left": state.player_titans_left, "titans_total": state.player_titans_total,
    }
