import pytest

from helpers import FINISHED, home, set_phase, set_token, track
from pyludo.engine.models import Phase
from pyludo.engine.rules import movable_tokens
from pyludo.engine.state import new_game


def test_a_six_is_required_to_leave_base():
    state = new_game(2)
    assert movable_tokens(state, 6) == [0, 1, 2, 3]
    assert movable_tokens(state, 5) == []


def test_tokens_on_the_track_can_move_with_any_die():
    state = set_token(new_game(2), 0, 2, track(10))
    assert movable_tokens(state, 3) == [2]
    assert movable_tokens(state, 6) == [0, 1, 2, 3]


def test_overshoot_excludes_a_token_near_home_while_others_remain_legal():
    state = new_game(2)
    state = set_token(state, 0, 0, home(4))  # progress 55
    state = set_token(state, 0, 1, track(10))
    assert movable_tokens(state, 2) == [1]  # token 0 would overshoot: 55 + 2 = 57 > 56


@pytest.mark.parametrize(
    ("pos", "die", "legal"),
    [
        # Boundary of "progress + die <= 56": landing exactly on 56 finishes the token.
        (track(50), 6, True),  # 50 + 6 = 56, from the last track square
        (home(0), 5, True),  # 51 + 5 = 56, from the home column
        (home(4), 1, True),  # 55 + 1 = 56, the smallest possible finishing roll
        # One past the boundary: overshoot.
        (home(0), 6, False),  # 51 + 6 = 57
        (home(4), 2, False),  # 55 + 2 = 57
    ],
)
def test_a_roll_that_lands_exactly_on_finished_is_legal(pos, die, legal):
    state = set_token(new_game(2), 0, 0, pos)
    assert (0 in movable_tokens(state, die)) is legal


def test_finished_tokens_never_move():
    state = set_token(new_game(2), 0, 0, FINISHED)
    assert 0 not in movable_tokens(state, 6)


def test_only_the_current_seats_tokens_are_considered():
    state = set_token(new_game(2), 1, 0, track(10))  # Yellow, but it's Red's turn
    assert movable_tokens(state, 3) == []


@pytest.mark.parametrize("die", [-4, 0, 7, 99])
def test_no_movable_tokens_for_a_die_outside_1_to_6(die):
    assert movable_tokens(new_game(2), die) == []


def test_no_movable_tokens_once_the_game_is_over():
    state = set_phase(new_game(2), Phase.GAME_OVER)
    assert movable_tokens(state, 6) == []
