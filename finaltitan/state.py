"""Game state dataclasses (enemy side only). No Streamlit imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Side = Literal["enemy", "players"]
Phase = Literal["start", "fight_start", "combat", "cleanup", "victory", "defeat"]

COUNT_TOKENS = ("armor", "poison", "fire", "power", "dodge", "minion", "action")


@dataclass
class Statuses:
    armor: int = 0
    poison: int = 0
    fire: int = 0
    power: int = 0
    dodge: int = 0
    minion: int = 0
    action: int = 0
    blessed_cursed: Literal["none", "blessed", "cursed"] = "none"


@dataclass
class EnemyTitan:
    card_id: str
    name: str
    max_life: int
    base_speed: int
    base_armor: int = 0
    team_power: bool = False
    legendary_id: str = ""
    life: int | None = None  # None while on the bench
    statuses: Statuses = field(default_factory=Statuses)
    charged: bool = False
    ultimate_form: bool = False
    legendary_upgrade: str | None = None
    speed_override: int | None = None

    @property
    def speed(self) -> int:
        return self.base_speed if self.speed_override is None else self.speed_override

    @property
    def armor(self) -> int:
        return self.base_armor + self.statuses.armor


@dataclass
class FightResult:
    reason: str  # enemy_defeated | player_defeated | both_defeated | enemy_returned | player_returned
    winner: Side | None
    enemy_id: str
    legendary: str | None = None


@dataclass
class LogEntry:
    index: int  # 1-based event number
    text: str
    kind: str = "event"  # event | hint


@dataclass
class Reveal:
    kind: Literal["titan", "upgrade"]
    card_id: str
    where: str = ""


@dataclass
class GameState:
    seed: int
    player_titans_total: int
    player_titans_left: int
    deck: list[EnemyTitan] = field(default_factory=list)  # hidden, index 0 is the top
    bench: list[EnemyTitan] = field(default_factory=list)  # queue, index 0 enters next
    upgrade_hand: list[str] = field(default_factory=list)  # hidden
    active_upgrades: list[str] = field(default_factory=list)
    new_upgrades: list[str] = field(default_factory=list)
    defeated: list[str] = field(default_factory=list)
    total: int = 0
    arena: EnemyTitan | None = None
    enemy_role: Literal["champion", "challenger"] | None = None
    phase: Phase = "start"
    active_side: Side | None = None
    turn_started: bool = False
    turn_no: int = 0
    fight_no: int = 1
    result: FightResult | None = None
    log: list[LogEntry] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    last_reveals: list[Reveal] = field(default_factory=list)
    event_count: int = 0

    def enemies(self) -> list[EnemyTitan]:
        return ([self.arena] if self.arena else []) + list(self.bench)

    def find(self, card_id: str) -> EnemyTitan | None:
        return next((t for t in self.enemies() if t.card_id == card_id), None)

    def enemy_remaining(self) -> int:
        return len(self.deck) + len(self.bench) + (1 if self.arena else 0)

    def in_fight(self) -> bool:
        return self.phase in ("fight_start", "combat") and self.arena is not None
