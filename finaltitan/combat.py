"""Generic combat rules as pure functions. No Streamlit imports."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DamageCalc:
    increased: int
    after_cancel: int
    after_armor: int
    final: int  # before Dodge and Minion
    armor_reduced: int


def damage_pipeline(base: int, power: int, bonus: int, cancel: bool, armor: int, replacement: int | None) -> DamageCalc:
    """Increase, cancel, Armor, replacement, in the order the rules define."""
    raw = base + bonus
    increased = raw + power if raw > 0 else max(raw, 0)
    after_cancel = 0 if cancel else increased
    after_armor = max(after_cancel - armor, 0)
    final = after_armor if replacement is None else max(replacement, 0)
    return DamageCalc(increased, after_cancel, after_armor, final, after_cancel - after_armor)


def prevention(damage: int, life: int, dodge: int, minion: int) -> tuple[int, str | None]:
    """Applies Dodge, then Minion (only if the damage would defeat). Returns damage and the token used."""
    if damage <= 0:
        return 0, None
    if dodge > 0:
        return 0, "dodge"
    if minion > 0 and damage >= life:
        return 0, "minion"
    return damage, None


def start_of_turn_damage(poison: int, fire: int) -> int:
    return poison + fire
