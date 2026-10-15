from typing import Final

from .models import Colour, PosKind, TokenPosition

# Board dimensions. Only the first three are independent; the rest are derived from them.
RING_SIZE: Final = 52  # squares on the shared ring
HOME_COLUMN_LENGTH: Final = 5  # squares in each colour's private home column
TOKENS_PER_PLAYER: Final = 4

# A colour walks one square short of the full ring, then turns into its home column.
TRACK_LENGTH: Final = RING_SIZE - 1  # relative track indices 0..50
FINISHED_PROGRESS: Final = TRACK_LENGTH + HOME_COLUMN_LENGTH  # 56

SAFE_SQUARES = frozenset({0, 8, 13, 21, 26, 34, 39, 47})

START_OFFSET: dict[Colour, int] = {
    Colour.RED: 0,
    Colour.GREEN: 13,
    Colour.YELLOW: 26,
    Colour.BLUE: 39,
}


def progress_of(pos: TokenPosition) -> int | None:
    match pos.kind:
        case PosKind.TRACK:
            return pos.index
        case PosKind.HOME_COLUMN:
            return pos.index + TRACK_LENGTH
        case PosKind.FINISHED:
            return FINISHED_PROGRESS
        case PosKind.BASE:
            return None


def position_from_progress(n: int) -> TokenPosition:
    if n in range(0, TRACK_LENGTH):
        return TokenPosition(PosKind.TRACK, n)
    if n in range(TRACK_LENGTH, FINISHED_PROGRESS):
        return TokenPosition(PosKind.HOME_COLUMN, n - TRACK_LENGTH)
    if n == FINISHED_PROGRESS:
        return TokenPosition(PosKind.FINISHED)
    raise ValueError(f"{n} outside the range 0..{FINISHED_PROGRESS}")


def absolute_of(colour: Colour, track_index: int) -> int:
    return (START_OFFSET[colour] + track_index) % RING_SIZE


def is_safe_absolute(n: int) -> bool:
    return n in SAFE_SQUARES
