"""Rules coach: guide(state, settings) -> Guidance. No Streamlit imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from .catalog import DATA_DIR
from .state import GameState

LEVELS = ["Beginner", "Expert"]
ACTOR_LABELS = {"enemy": "ENEMY", "players": "PLAYERS", "all": "EVERYONE"}


@dataclass
class GuidanceSettings:
    level: str = "Beginner"


@dataclass
class PrimaryAction:
    label: str
    kind: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Guidance:
    step: str
    actor_kind: str  # enemy | players | all
    actor_label: str
    lines: list[str] = field(default_factory=list)
    why: str = ""
    refs: list[tuple[str, str]] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    primary: list[PrimaryAction] = field(default_factory=list)
    confirms: list[str] = field(default_factory=list)  # Beginner: one button per line before the last


@lru_cache(maxsize=1)
def _load_texts(mtime: float) -> dict[str, Any]:
    with open(DATA_DIR / "guide.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _texts() -> dict[str, Any]:
    return _load_texts((DATA_DIR / "guide.yaml").stat().st_mtime)


class _Ctx(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _fmt(text: str, ctx: dict[str, Any]) -> str:
    return text.format_map(_Ctx(ctx)).strip()


def step_of(state: GameState) -> str:
    if state.phase == "start":
        return "setup"
    if state.phase in ("victory", "defeat"):
        return state.phase
    if state.phase == "fight_start":
        return "fight_start_champion" if state.enemy_role == "champion" else "fight_start_challenger"
    if state.phase == "cleanup":
        return f"cleanup_{state.result.reason}" if state.result else "cleanup_both_defeated"
    if state.active_side == "players":
        return "players_turn"
    return "enemy_turn" if state.turn_started else "enemy_turn_start"


def _name(state: GameState, card_id: str | None) -> str:
    if not card_id:
        return ""
    t = state.find(card_id)
    if t is not None:
        return t.name
    return next((t.name for t in state.deck if t.card_id == card_id), card_id)


def _next_line(state: GameState) -> str:
    if state.player_titans_left == 0 or state.enemy_remaining() == 0:
        return ""
    reveal = "A new enemy Upgrade is revealed"
    if state.upgrade_hand and state.enemy_remaining() == 1 and len(state.upgrade_hand) > 1:
        reveal = "All remaining enemy Upgrades are revealed for the final fight"
    elif not state.upgrade_hand:
        reveal = "No enemy Upgrades are left to reveal"
    if state.arena is not None:
        return f"**Next:** {reveal}. Then choose your next Challenger."
    return f"**Next:** {reveal}, then the next enemy enters."


def _context(state: GameState) -> dict[str, Any]:
    t = state.arena
    ctx: dict[str, Any] = {"left": state.player_titans_left, "total": state.player_titans_total}
    if state.result is not None:
        ctx["enemy"] = _name(state, state.result.enemy_id)
        if state.result.legendary:
            ctx["legendary_line"] = "It had a Legendary Upgrade: that player also takes it."
    if t is not None:
        ctx["enemy"] = t.name
        ctx["speed"] = t.speed
        actions = 1 + t.statuses.action
        ctx["actions"] = actions
        ctx["action_word"] = "Action" if actions == 1 else "Actions"
        dmg = t.statuses.poison + t.statuses.fire
        if dmg:
            ctx["tick_line"] = f"Poison {t.statuses.poison} and Fire {t.statuses.fire} deal {dmg} damage to the enemy now."
        bc = t.statuses.blessed_cursed
        if bc == "blessed":
            ctx["dice_line"] = "The enemy is Blessed: roll two dice per Action and use the one that is best for the enemy."
        elif bc == "cursed":
            ctx["dice_line"] = "The enemy is Cursed: roll two dice per Action; you choose which one counts. On doubles, remove the token."
    if state.phase == "cleanup":
        ctx["next_line"] = _next_line(state)
    return ctx


def _hints(state: GameState) -> list[str]:
    hints = list(state.hints)
    t = state.arena
    if t is not None and state.phase == "combat":
        if t.statuses.power:
            hints.append(f"Enemy damage is increased by {t.statuses.power} (Power).")
        if t.armor:
            hints.append(f"Enemy Armor {t.armor} reduces each damage you deal by {t.armor}.")
    for b in state.bench:
        if b.team_power:
            hints.append(f"{b.name} on the enemy bench has a Team Power. It is active for the enemy.")
    if state.phase in ("fight_start", "combat") and state.enemy_remaining() == 1:
        hints.append("Final fight: this is the last enemy Titan.")
    hints.append("When a card contradicts the rules, the card wins.")
    return hints


def guide(state: GameState, settings: GuidanceSettings) -> Guidance:
    step = step_of(state)
    spec = _texts()["steps"][step]
    kind = spec.get("actor", "all")
    g = Guidance(step=step, actor_kind=kind, actor_label=ACTOR_LABELS[kind])
    g.primary = [PrimaryAction(label, k, dict(args or {})) for label, k, args in spec.get("primary", [])]
    ctx = _context(state)

    if settings.level == "Expert":
        short = _fmt(spec["short"], ctx)
        g.lines = [short] if short else []
        return g
    g.lines = [text for text in (_fmt(raw, ctx) for raw in spec["lines"]) if text]
    g.confirms = list(spec.get("confirms", []))
    g.why = _fmt(spec.get("why", ""), ctx)
    g.refs = [(a, b) for a, b in spec.get("refs", [])]
    g.hints = _hints(state)
    return g
