from itertools import pairwise

import pytest

from helpers import BASE, FINISHED, home, track
from pyludo.board_layout import (
    CENTRE,
    GRID_SIZE,
    YARD_ORIGIN,
    Cell,
    base_cell,
    cell_for,
    home_column_cell,
    rotate_clockwise,
    track_cell,
)
from pyludo.engine.models import Colour

ALL_TRACK = [track_cell(i) for i in range(52)]
ALL_HOME = [home_column_cell(c, i) for c in Colour for i in range(5)]
ALL_BASE = [base_cell(c, i) for c in Colour for i in range(4)]


def _touching(a: Cell, b: Cell) -> bool:
    """Neighbours on the grid, including diagonally."""
    return max(abs(a.row - b.row), abs(a.col - b.col)) == 1


# --- Cell ------------------------------------------------------------------


def test_cell_is_a_named_tuple_of_row_and_col():
    cell = Cell(6, 1)
    assert cell == (6, 1)
    assert (cell.row, cell.col) == (6, 1)
    row, col = cell
    assert (row, col) == (6, 1)


def test_grid_and_centre():
    assert GRID_SIZE == 15
    assert CENTRE == (7, 7)


# --- rotate_clockwise ------------------------------------------------------


def test_rotating_clockwise_turns_reds_start_into_greens_start():
    assert rotate_clockwise(Cell(6, 1)) == (1, 8)
    assert isinstance(rotate_clockwise(Cell(6, 1)), Cell)


def test_rotating_clockwise_keeps_the_centre_in_place():
    assert rotate_clockwise(CENTRE) == CENTRE


@pytest.mark.parametrize("cell", ALL_TRACK)
def test_four_rotations_are_a_full_turn(cell):
    assert rotate_clockwise(rotate_clockwise(rotate_clockwise(rotate_clockwise(cell)))) == cell


# --- Track -----------------------------------------------------------------


def test_reds_arm_is_hand_placed():
    assert [track_cell(i) for i in range(13)] == [
        (6, 1), (6, 2), (6, 3), (6, 4), (6, 5),
        (5, 6), (4, 6), (3, 6), (2, 6), (1, 6), (0, 6),
        (0, 7), (0, 8),
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("absolute", "cell"),
    [
        (13, (1, 8)),  # Green's start
        (26, (8, 13)),  # Yellow's start
        (39, (13, 6)),  # Blue's start
        (50, (7, 0)),  # Red's last track square, just before its home column
        (51, (6, 0)),  # Red never stands here; the others pass through
    ],
)
def test_other_arms_come_from_rotation(absolute, cell):
    assert track_cell(absolute) == cell


def test_the_track_has_52_distinct_cells_inside_the_grid():
    assert len(set(ALL_TRACK)) == 52
    assert all(0 <= r < 15 and 0 <= c < 15 for r, c in ALL_TRACK)


def test_consecutive_track_squares_touch_and_the_ring_closes():
    for i in range(52):
        assert _touching(ALL_TRACK[i], ALL_TRACK[(i + 1) % 52]), i


@pytest.mark.parametrize(
    ("absolute", "cell"),
    [
        (0, (6, 1)),
        (8, (2, 6)),
        (13, (1, 8)),
        (21, (6, 12)),
        (26, (8, 13)),
        (34, (12, 8)),
        (39, (13, 6)),
        (47, (8, 2)),
    ],
)
def test_safe_squares_sit_where_the_board_diagram_puts_stars(absolute, cell):
    assert track_cell(absolute) == cell


@pytest.mark.parametrize("absolute", [-1, 52, 100])
def test_track_cell_rejects_an_index_outside_0_to_51(absolute):
    with pytest.raises(ValueError):
        track_cell(absolute)


# --- Home columns ----------------------------------------------------------


@pytest.mark.parametrize(
    ("colour", "cells"),
    [
        (Colour.RED, [(7, 1), (7, 2), (7, 3), (7, 4), (7, 5)]),
        (Colour.GREEN, [(1, 7), (2, 7), (3, 7), (4, 7), (5, 7)]),
        (Colour.YELLOW, [(7, 13), (7, 12), (7, 11), (7, 10), (7, 9)]),
        (Colour.BLUE, [(13, 7), (12, 7), (11, 7), (10, 7), (9, 7)]),
    ],
)
def test_home_columns_run_towards_the_centre(colour, cells):
    assert [home_column_cell(colour, i) for i in range(5)] == cells


@pytest.mark.parametrize("colour", list(Colour))
def test_a_home_column_leads_from_its_colours_last_track_square_to_the_centre(colour):
    column = [home_column_cell(colour, i) for i in range(5)]
    assert _touching(cell_for(colour, 0, track(50)), column[0])
    # A straight line of single steps...
    step = (column[1].row - column[0].row, column[1].col - column[0].col)
    assert abs(step[0]) + abs(step[1]) == 1
    for a, b in pairwise(column):
        assert (b.row - a.row, b.col - a.col) == step
    # ...that would reach the centre two steps after the last square (the 3x3 centre
    # block sits in between on screen).
    assert (column[4].row + 2 * step[0], column[4].col + 2 * step[1]) == CENTRE


@pytest.mark.parametrize("index", [-1, 5])
def test_home_column_cell_rejects_an_index_outside_0_to_4(index):
    with pytest.raises(ValueError):
        home_column_cell(Colour.RED, index)


# --- Yards and bases -------------------------------------------------------


def test_yard_origins_are_the_top_left_of_each_6x6_corner():
    assert YARD_ORIGIN == {
        Colour.RED: (0, 0),
        Colour.GREEN: (0, 9),
        Colour.YELLOW: (9, 9),
        Colour.BLUE: (9, 0),
    }


@pytest.mark.parametrize(
    ("colour", "cells"),
    [
        # Reading order inside the yard: top-left, top-right, bottom-left, bottom-right.
        (Colour.RED, [(1, 1), (1, 4), (4, 1), (4, 4)]),
        (Colour.GREEN, [(1, 10), (1, 13), (4, 10), (4, 13)]),
        (Colour.YELLOW, [(10, 10), (10, 13), (13, 10), (13, 13)]),
        (Colour.BLUE, [(10, 1), (10, 4), (13, 1), (13, 4)]),
    ],
)
def test_base_slots_are_in_reading_order(colour, cells):
    assert [base_cell(colour, i) for i in range(4)] == cells


@pytest.mark.parametrize("colour", list(Colour))
def test_base_slots_sit_inside_their_own_yard(colour):
    top, left = YARD_ORIGIN[colour]
    for i in range(4):
        row, col = base_cell(colour, i)
        assert top <= row < top + 6
        assert left <= col < left + 6


@pytest.mark.parametrize("token_index", [-1, 4])
def test_base_cell_rejects_an_index_outside_0_to_3(token_index):
    with pytest.raises(ValueError):
        base_cell(Colour.RED, token_index)


def test_no_two_squares_share_a_cell():
    every = ALL_TRACK + ALL_HOME + ALL_BASE + [CENTRE]
    assert len(every) == 52 + 20 + 16 + 1
    assert len(set(every)) == len(every)


# --- cell_for: engine position -> board cell -------------------------------


@pytest.mark.parametrize("token_index", range(4))
def test_cell_for_a_token_in_base_is_its_own_base_slot(token_index):
    assert cell_for(Colour.GREEN, token_index, BASE) == base_cell(Colour.GREEN, token_index)


@pytest.mark.parametrize(
    ("colour", "index", "cell"),
    [
        (Colour.RED, 0, (6, 1)),
        (Colour.GREEN, 0, (1, 8)),  # relative 0 is the colour's own start
        (Colour.RED, 5, (5, 6)),  # absolute 5...
        (Colour.YELLOW, 31, (5, 6)),  # ...is also Yellow's track 31: (26 + 31) % 52 = 5
        (Colour.GREEN, 50, (0, 7)),  # wraps: (13 + 50) % 52 = 11
    ],
)
def test_cell_for_a_track_token_uses_its_absolute_square(colour, index, cell):
    assert cell_for(colour, 0, track(index)) == cell


def test_cell_for_a_home_column_token():
    assert cell_for(Colour.RED, 0, home(4)) == (7, 5)
    assert cell_for(Colour.BLUE, 2, home(0)) == (13, 7)


@pytest.mark.parametrize("colour", list(Colour))
def test_cell_for_a_finished_token_is_the_centre(colour):
    assert cell_for(colour, 3, FINISHED) == CENTRE
