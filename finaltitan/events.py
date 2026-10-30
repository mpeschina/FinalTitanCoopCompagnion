"""Event types. The game state is reduce(initial_state, actions)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BEGIN_GAME = "begin_game"
SET_STARTER = "set_starter"
START_TURN = "start_turn"
END_TURN = "end_turn"
DAMAGE = "damage"
HEAL = "heal"
LIFE_ADJUST = "life_adjust"
TOKEN = "token"
FLAG = "flag"
SPEED = "speed"
FIGHT_END = "fight_end"
SWAP = "swap"
ADD_ENEMY_UPGRADE = "add_enemy_upgrade"
NOTE = "note"
ADVANCE_FIGHT = "advance_fight"


@dataclass
class Action:
    kind: str
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "args": self.args}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Action":
        return Action(str(data["kind"]), dict(data.get("args", {})))


def act(kind: str, **args: Any) -> Action:
    return Action(kind, args)
