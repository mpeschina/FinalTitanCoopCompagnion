"""Game setup: difficulty table, presets, and enemy deck building. No Streamlit imports."""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .catalog import DATA_DIR, Catalog

DIFFICULTIES = ["Easy", "Standard", "Hard", "Very Hard", "Insane"]
# enemy Titans per difficulty, indexed by player count - 1
ENEMY_COUNT = {
    "Easy": (2, 4, 6),
    "Standard": (3, 5, 7),
    "Hard": (4, 6, 8),
    "Very Hard": (5, 7, 9),
    "Insane": (6, 8, 10),
}
TITANS_PER_PLAYER = 3
MAX_PLAYERS = 3


@dataclass
class GameSetup:
    players: int = 1
    difficulty: str = "Standard"
    seed: int = 1
    expansions: list[str] = field(default_factory=list)
    advanced: bool = False
    preset: str | None = None
    player_titans: list[str] = field(default_factory=list)  # excluded from the enemy pool
    enemy_titans: list[str] = field(default_factory=list)
    enemy_upgrades: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "GameSetup":
        base = GameSetup()
        for key in asdict(base):
            if key in data:
                setattr(base, key, data[key])
        return base

    def enemy_count(self) -> int:
        return ENEMY_COUNT[self.difficulty][self.players - 1]

    def player_titan_count(self) -> int:
        return self.players * TITANS_PER_PLAYER

    def drafted(self) -> set[str]:
        return set(self.player_titans)

    def draft_complete(self) -> bool:
        return len(self.player_titans) == self.player_titan_count()


def load_presets(path: Path = DATA_DIR / "presets.yaml") -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def preset_deck(preset: dict[str, Any], players: int) -> dict[str, list[str]] | None:
    return (preset.get("decks") or {}).get(players)


def reserved_titans(setup: GameSetup, catalog: Catalog, presets: dict[str, dict[str, Any]]) -> set[str]:
    """Titan ids a preset gives the enemy, which players must not draft."""
    if not setup.preset or setup.preset not in presets:
        return set()
    deck = preset_deck(presets[setup.preset], setup.players)
    if not deck:
        return set()
    ids: set[str] = set()
    for name in deck["titans"]:
        found = catalog.find_card(name, "titan")
        if found:
            ids.add(found[0])
    return ids


def _in_scope(card: Any, setup: GameSetup) -> bool:
    if setup.expansions and card.expansion not in setup.expansions:
        return False
    return setup.advanced or not card.advanced


def build_enemy(setup: GameSetup, catalog: Catalog, presets: dict[str, dict[str, Any]]) -> list[str]:
    """Fills setup.enemy_titans and enemy_upgrades. Returns warnings for the players."""
    rng = random.Random(setup.seed)
    warnings: list[str] = []
    n = setup.enemy_count()
    drafted = setup.drafted()
    titan_pool = sorted(
        t.id for t in catalog.titans.values() if t.enemy_usable and t.id not in drafted and _in_scope(t, setup)
    )
    upgrade_pool = sorted(u.id for u in catalog.upgrades.values() if u.enemy_usable and _in_scope(u, setup))

    deck = preset_deck(presets[setup.preset], setup.players) if setup.preset in presets else None
    titans: list[str] = []
    upgrades: list[str] = []
    if deck:
        n = len(deck["titans"])
        for name in deck["titans"]:
            found = catalog.find_card(name, "titan")
            if found:
                titans.append(found[0])
            else:
                warnings.append("A preset Titan has no image in assets and was replaced by a random Titan.")
                titans.append("")
        for name in deck["upgrades"]:
            found = catalog.find_card(name, "upgrade")
            if found:
                upgrades.append(found[0])
            else:
                warnings.append("A preset Upgrade has no image in assets and was replaced by a random Upgrade.")
                upgrades.append("")

    free_titans = [t for t in titan_pool if t not in titans and t not in drafted]
    rng.shuffle(free_titans)
    free_upgrades = [u for u in upgrade_pool if u not in upgrades]
    rng.shuffle(free_upgrades)

    if not deck:
        if len(free_titans) < n:
            raise ValueError(f"Not enough enemy-usable Titans in the pool ({len(free_titans)} for {n}).")
        titans = free_titans[:n]
        if len(free_upgrades) < n:
            raise ValueError(f"Not enough enemy-usable Upgrades in the pool ({len(free_upgrades)} for {n}).")
        upgrades = free_upgrades[:n]
    else:
        titans = [t or free_titans.pop() for t in titans]
        upgrades = [u or free_upgrades.pop() for u in upgrades]

    setup.enemy_titans = titans
    setup.enemy_upgrades = upgrades
    return warnings
