import dataclasses

import pytest

from pyludo.engine.errors import InvalidPlayerCountError
from pyludo.engine.models import Colour, Phase, PosKind
from pyludo.engine.state import new_game


@pytest.mark.parametrize(
    ("count", "colours"),
    [
        (2, [Colour.RED, Colour.YELLOW]),  # opposite corners
        (3, [Colour.RED, Colour.GREEN, Colour.YELLOW]),
        (4, [Colour.RED, Colour.GREEN, Colour.YELLOW, Colour.BLUE]),
    ],
)
def test_new_game_assigns_colours_by_player_count(count, colours):
    state = new_game(count)
    assert state.player_count == count
    assert len(state.players) == count  # no padding to 4 like the C++ std::array
    assert [p.colour for p in state.players] == colours


def test_new_game_starts_every_token_in_base_awaiting_a_roll():
    state = new_game(4)
    for player in state.players:
        assert len(player.tokens) == 4
        assert all(t.kind == PosKind.BASE for t in player.tokens)
    assert state.current_seat == 0
    assert state.phase == Phase.AWAITING_ROLL
    assert state.pending_die is None
    assert state.winner is None


@pytest.mark.parametrize("count", [-1, 0, 1, 5, 10])
def test_new_game_rejects_a_player_count_outside_2_to_4(count):
    with pytest.raises(InvalidPlayerCountError):
        new_game(count)


def test_state_is_deeply_immutable():
    state = new_game(2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.current_seat = 1  # type: ignore[misc]
    # hash() only succeeds if every field all the way down is immutable,
    # so this fails if players or tokens are lists instead of tuples.
    hash(state)
