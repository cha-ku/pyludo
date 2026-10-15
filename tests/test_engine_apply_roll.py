from dataclasses import replace

import pytest

from helpers import FINISHED, home, set_phase, set_token
from pyludo.engine.errors import DieOutOfRangeError, GameOverError, NotAwaitingRollError
from pyludo.engine.models import Phase
from pyludo.engine.rules import apply_move, apply_roll
from pyludo.engine.state import new_game


def test_a_roll_with_movable_tokens_waits_for_a_move():
    state = apply_roll(new_game(2), 6)
    assert state.current_seat == 0
    assert state.phase == Phase.AWAITING_MOVE
    assert state.pending_die == 6


def test_any_number_of_consecutive_sixes_keeps_granting_extra_rolls():
    state = new_game(2)
    for _ in range(5):
        state = apply_roll(state, 6)
        assert state.current_seat == 0
        assert state.phase == Phase.AWAITING_MOVE

        state = apply_move(state, 0)
        assert state.current_seat == 0  # no three-sixes rule
        assert state.phase == Phase.AWAITING_ROLL


def test_no_legal_move_passes_the_turn_automatically():
    state = apply_roll(new_game(2), 3)  # every token is still in base
    assert state.current_seat == 1
    assert state.phase == Phase.AWAITING_ROLL
    assert state.pending_die is None


def test_passing_the_turn_wraps_around_to_seat_zero():
    state = replace(new_game(3), current_seat=2)
    assert apply_roll(state, 3).current_seat == 0


def test_a_six_with_no_legal_move_still_passes_the_turn():
    state = new_game(2)
    state = set_token(state, 0, 0, home(3))  # progress 54; 54 + 6 = 60 overshoots
    for token in (1, 2, 3):
        state = set_token(state, 0, token, FINISHED)

    state = apply_roll(state, 6)
    assert state.current_seat == 1
    assert state.phase == Phase.AWAITING_ROLL


@pytest.mark.parametrize("die", [0, 7])
def test_apply_roll_rejects_an_out_of_range_die(die):
    with pytest.raises(DieOutOfRangeError):
        apply_roll(new_game(2), die)


def test_apply_roll_rejects_being_called_twice_without_a_move_in_between():
    rolled = apply_roll(new_game(2), 6)
    with pytest.raises(NotAwaitingRollError):
        apply_roll(rolled, 4)


def test_apply_roll_on_a_finished_game_reports_game_over():
    state = set_phase(new_game(2), Phase.GAME_OVER)
    with pytest.raises(GameOverError):
        apply_roll(state, 4)
