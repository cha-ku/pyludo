from typing import NamedTuple

from .engine.models import Colour, PosKind, TokenPosition
from .engine.path import HOME_COLUMN_LENGTH, RING_SIZE, TOKENS_PER_PLAYER, absolute_of


class Cell(NamedTuple):
    row: int
    col: int


GRID_SIZE = 15
CENTRE = Cell(7, 7)
YARD_ORIGIN = {
    Colour.RED: Cell(0, 0),
    Colour.GREEN: Cell(0, 9),
    Colour.YELLOW: Cell(9, 9),
    Colour.BLUE: Cell(9, 0),
}
_BASE_SLOTS = {
    Colour.RED: (Cell(1, 1), Cell(1, 4), Cell(4, 1), Cell(4, 4)),
    Colour.GREEN: (Cell(1, 10), Cell(1, 13), Cell(4, 10), Cell(4, 13)),
    Colour.YELLOW: (Cell(10, 10), Cell(10, 13), Cell(13, 10), Cell(13, 13)),
    Colour.BLUE: (Cell(10, 1), Cell(10, 4), Cell(13, 1), Cell(13, 4)),
}


def rotate_clockwise(cell: Cell) -> Cell:
    return Cell(cell.col, (GRID_SIZE - 1) - cell.row)


def _generate_track() -> tuple[Cell, ...]:
    red = (
        Cell(6, 1),
        Cell(6, 2),
        Cell(6, 3),
        Cell(6, 4),
        Cell(6, 5),
        Cell(5, 6),
        Cell(4, 6),
        Cell(3, 6),
        Cell(2, 6),
        Cell(1, 6),
        Cell(0, 6),
        Cell(0, 7),
        Cell(0, 8),
    )
    green = tuple(rotate_clockwise(c) for c in red)
    yellow = tuple(rotate_clockwise(c) for c in green)
    blue = tuple(rotate_clockwise(c) for c in yellow)
    return red + green + yellow + blue


TRACK = _generate_track()


def track_cell(absolute: int) -> Cell:
    if not 0 <= absolute < RING_SIZE:
        raise ValueError(f"value should be between 0 and {RING_SIZE - 1}, got {absolute}")
    return TRACK[absolute]


def base_cell(colour: Colour, index: int) -> Cell:
    if not 0 <= index < TOKENS_PER_PLAYER:
        raise ValueError(f"value should be between 0 and {TOKENS_PER_PLAYER - 1}, got {index}")
    return _BASE_SLOTS[colour][index]


def _generate_home_column() -> dict[Colour, tuple[Cell, ...]]:
    red = (Cell(7, 1), Cell(7, 2), Cell(7, 3), Cell(7, 4), Cell(7, 5))
    green = tuple(rotate_clockwise(c) for c in red)
    yellow = tuple(rotate_clockwise(c) for c in green)
    blue = tuple(rotate_clockwise(c) for c in yellow)
    return {Colour.RED: red, Colour.GREEN: green, Colour.YELLOW: yellow, Colour.BLUE: blue}


_HOME_COLUMNS = _generate_home_column()


def home_column_cell(colour: Colour, index: int) -> Cell:
    if not 0 <= index < HOME_COLUMN_LENGTH:
        raise ValueError(f"value should be between 0 and {HOME_COLUMN_LENGTH - 1}, got {index}")
    return _HOME_COLUMNS[colour][index]


def cell_for(colour: Colour, token_index: int, pos: TokenPosition) -> Cell:
    match pos.kind:
        case PosKind.BASE:
            return base_cell(colour, token_index)
        case PosKind.TRACK:
            return track_cell(absolute_of(colour, pos.index))
        case PosKind.HOME_COLUMN:
            return home_column_cell(colour, pos.index)
        case PosKind.FINISHED:
            return CENTRE
