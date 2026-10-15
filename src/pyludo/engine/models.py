from dataclasses import dataclass
from enum import Enum, StrEnum


class Colour(StrEnum):
    RED = "red"
    GREEN = "green"
    YELLOW = "yellow"
    BLUE = "blue"


class PosKind(Enum):
    BASE = "BASE"
    TRACK = "TRACK"
    HOME_COLUMN = "HOME_COLUMN"
    FINISHED = "FINISHED"


class Phase(Enum):
    AWAITING_ROLL = "AWAITING_ROLL"
    AWAITING_MOVE = "AWAITING_MOVE"
    GAME_OVER = "GAME_OVER"


@dataclass(frozen=True)
class TokenPosition:
    kind: PosKind
    index: int = 0

    def __post_init__(self):
        if self.kind in (PosKind.BASE, PosKind.FINISHED):
            object.__setattr__(self, "index", 0)
