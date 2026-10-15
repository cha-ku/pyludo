import pytest

from pyludo.engine.models import Colour, PosKind, TokenPosition
from pyludo.engine.path import (
    SAFE_SQUARES,
    absolute_of,
    is_safe_absolute,
    position_from_progress,
    progress_of,
)


@pytest.mark.parametrize("progress", range(57))
def test_progress_round_trips_through_track_and_home_column(progress):
    assert progress_of(position_from_progress(progress)) == progress


@pytest.mark.parametrize(
    ("progress", "kind"),
    [
        (0, PosKind.TRACK),
        (50, PosKind.TRACK),
        (51, PosKind.HOME_COLUMN),
        (55, PosKind.HOME_COLUMN),
        (56, PosKind.FINISHED),
    ],
)
def test_progress_boundaries_map_to_the_right_kind(progress, kind):
    assert position_from_progress(progress).kind == kind


def test_home_column_index_starts_at_zero():
    assert position_from_progress(51) == TokenPosition(PosKind.HOME_COLUMN, 0)
    assert position_from_progress(55) == TokenPosition(PosKind.HOME_COLUMN, 4)


@pytest.mark.parametrize("progress", [-1, 57, 100])
def test_position_from_progress_rejects_out_of_range(progress):
    # The C++ version used assert(). In Python a bad argument is a ValueError,
    # because asserts are stripped when Python runs with -O.
    with pytest.raises(ValueError):
        position_from_progress(progress)


def test_base_has_no_progress():
    assert progress_of(TokenPosition(PosKind.BASE)) is None


def test_absolute_of_applies_each_colours_start_offset():
    assert absolute_of(Colour.RED, 0) == 0
    assert absolute_of(Colour.GREEN, 0) == 13
    assert absolute_of(Colour.YELLOW, 0) == 26
    assert absolute_of(Colour.BLUE, 0) == 39
    assert absolute_of(Colour.BLUE, 20) == (39 + 20) % 52


def test_safe_squares():
    assert SAFE_SQUARES == frozenset({0, 8, 13, 21, 26, 34, 39, 47})
    for square in SAFE_SQUARES:
        assert is_safe_absolute(square)
    for square in (1, 14, 25, 40, 7, 22):
        assert not is_safe_absolute(square)
