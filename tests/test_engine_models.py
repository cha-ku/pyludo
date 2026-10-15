import dataclasses

import pytest

from pyludo.engine import errors
from pyludo.engine.models import Colour, Phase, PosKind, TokenPosition


def test_colours_are_lowercase_strings():
    # The M4 wire protocol sends colours as JSON strings. With a StrEnum,
    # json.dumps(Colour.RED) works without a custom encoder.
    assert [c.value for c in Colour] == ["red", "green", "yellow", "blue"]
    assert Colour.RED == "red"


def test_colours_are_distinct_and_usable_as_dict_keys():
    # path.py will map each colour to its start offset with a dict.
    assert Colour.RED != Colour.GREEN
    offsets = {Colour.RED: 0, Colour.GREEN: 13, Colour.YELLOW: 26, Colour.BLUE: 39}
    assert len(offsets) == 4
    assert offsets[Colour.RED] == 0


def test_enums_have_expected_members():
    assert {k.name for k in PosKind} == {"BASE", "TRACK", "HOME_COLUMN", "FINISHED"}
    assert {p.name for p in Phase} == {"AWAITING_ROLL", "AWAITING_MOVE", "GAME_OVER"}


def test_index_defaults_to_zero():
    assert TokenPosition(PosKind.TRACK).index == 0


def test_equality_ignores_index_for_base_and_finished():
    # There is only one Base and one Finished per token, so the index is meaningless there.
    assert TokenPosition(PosKind.BASE, 0) == TokenPosition(PosKind.BASE, 3)
    assert TokenPosition(PosKind.FINISHED, 0) == TokenPosition(PosKind.FINISHED, 9)
    assert TokenPosition(PosKind.TRACK, 0) != TokenPosition(PosKind.TRACK, 3)
    assert TokenPosition(PosKind.TRACK, 3) != TokenPosition(PosKind.HOME_COLUMN, 3)


def test_equal_positions_have_equal_hashes():
    # Python's contract: a == b must imply hash(a) == hash(b), otherwise sets and dicts break.
    assert len({TokenPosition(PosKind.BASE, 0), TokenPosition(PosKind.BASE, 3)}) == 1
    assert len({TokenPosition(PosKind.TRACK, 0), TokenPosition(PosKind.TRACK, 3)}) == 2


def test_token_position_is_frozen():
    pos = TokenPosition(PosKind.TRACK, 5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        pos.index = 6  # type: ignore[misc]


ERRORS = [
    (
        errors.InvalidPlayerCountError,
        "invalid_player_count",
        "player count must be between 2 and 4",
    ),
    (errors.GameOverError, "game_over", "game is over"),
    (errors.NotAwaitingRollError, "not_awaiting_roll", "not awaiting a roll"),
    (errors.NotAwaitingMoveError, "not_awaiting_move", "not awaiting a move"),
    (errors.DieOutOfRangeError, "die_out_of_range", "die must be between 1 and 6"),
    (errors.InvalidTokenIndexError, "invalid_token_index", "token index must be between 0 and 3"),
    (errors.IllegalMoveError, "illegal_move", "move is not legal for the pending die"),
]


@pytest.mark.parametrize(("cls", "code", "message"), ERRORS)
def test_engine_errors_carry_a_code_and_default_message(cls, code, message):
    # `code` is the stable, machine-readable part (the server will send it to the browser);
    # the message is free to be reworded later.
    assert issubclass(cls, errors.LudoError)
    assert issubclass(errors.LudoError, Exception)
    err = cls()
    assert err.code == code
    assert str(err) == message
