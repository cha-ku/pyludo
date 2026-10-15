import pytest

from helpers import BASE, FINISHED, home, set_phase, set_token, track
from pyludo.engine.errors import (
    DieOutOfRangeError,
    GameOverError,
    IllegalMoveError,
    InvalidTokenIndexError,
    NotAwaitingMoveError,
)
from pyludo.engine.models import Colour, Phase, PosKind
from pyludo.engine.rules import apply_move, apply_roll
from pyludo.engine.state import new_game

# --- validation ---------------------------------------------------------------


def test_apply_move_rejects_a_move_not_in_the_legal_set():
    state = set_phase(new_game(2), Phase.AWAITING_MOVE, 3)  # nothing can leave base on a 3
    with pytest.raises(IllegalMoveError):
        apply_move(state, 0)


@pytest.mark.parametrize("token", [-1, 4, 99])
def test_apply_move_rejects_a_token_index_outside_0_to_3(token):
    state = set_phase(new_game(2), Phase.AWAITING_MOVE, 6)
    with pytest.raises(InvalidTokenIndexError):
        apply_move(state, token)


@pytest.mark.parametrize("die", [-4, 0, 7, None])
def test_apply_move_rejects_a_pending_die_outside_1_to_6(die):
    state = set_token(new_game(2), 0, 0, track(10))
    state = set_phase(state, Phase.AWAITING_MOVE, die)
    with pytest.raises(DieOutOfRangeError):
        apply_move(state, 0)


def test_apply_move_when_a_roll_is_expected_reports_not_awaiting_move():
    with pytest.raises(NotAwaitingMoveError):
        apply_move(new_game(2), 0)


def test_apply_move_on_a_finished_game_reports_game_over_not_not_awaiting_move():
    state = set_phase(new_game(2), Phase.GAME_OVER)
    with pytest.raises(GameOverError):
        apply_move(state, 0)


# --- movement -----------------------------------------------------------------


def test_leaving_base_lands_on_track_zero_and_consumes_the_whole_die():
    state = set_phase(new_game(2), Phase.AWAITING_MOVE, 6)
    state = apply_move(state, 0)
    assert state.players[0].tokens[0] == track(0)
    assert state.pending_die is None


def test_apply_move_does_not_modify_its_input():
    before = set_phase(new_game(2), Phase.AWAITING_MOVE, 6)
    apply_move(before, 0)
    assert before.players[0].tokens[0] == BASE
    assert before.phase == Phase.AWAITING_MOVE


def test_a_normal_move_passes_the_turn():
    state = set_token(new_game(2), 0, 0, track(10))
    state = apply_move(set_phase(state, Phase.AWAITING_MOVE, 3), 0)
    assert state.players[0].tokens[0] == track(13)
    assert state.current_seat == 1
    assert state.phase == Phase.AWAITING_ROLL


def test_exact_roll_moves_a_token_into_the_home_column():
    state = set_token(new_game(2), 0, 0, track(48))
    state = apply_move(set_phase(state, Phase.AWAITING_MOVE, 6), 0)
    assert state.players[0].tokens[0] == home(3)


def test_entering_the_home_column_without_finishing_does_not_grant_an_extra_roll():
    state = set_token(new_game(2), 0, 0, track(47))
    state = apply_move(set_phase(state, Phase.AWAITING_MOVE, 4), 0)  # 47 + 4 = 51
    assert state.players[0].tokens[0] == home(0)
    assert state.current_seat == 1


def test_exact_roll_finishes_a_token_and_grants_an_extra_roll():
    state = set_token(new_game(2), 0, 0, track(50))
    state = apply_move(set_phase(state, Phase.AWAITING_MOVE, 6), 0)
    assert state.players[0].tokens[0].kind == PosKind.FINISHED
    assert state.current_seat == 0
    assert state.phase == Phase.AWAITING_ROLL


def test_reaching_home_with_a_non_six_still_grants_an_extra_roll():
    state = set_token(new_game(2), 0, 0, home(2))
    state = apply_move(set_phase(state, Phase.AWAITING_MOVE, 3), 0)  # 53 + 3 = 56
    assert state.players[0].tokens[0].kind == PosKind.FINISHED
    assert state.current_seat == 0
    assert state.phase == Phase.AWAITING_ROLL


# --- captures -----------------------------------------------------------------


def test_landing_on_an_opponent_on_a_normal_square_sends_it_back_to_base():
    state = new_game(2)  # seat 0 Red, seat 1 Yellow
    state = set_token(state, 0, 0, track(3))  # Red absolute 3
    state = set_token(state, 1, 0, track(31))  # Yellow absolute (26 + 31) % 52 = 5
    state = apply_move(set_phase(state, Phase.AWAITING_MOVE, 2), 0)

    assert state.players[0].tokens[0] == track(5)
    assert state.players[1].tokens[0] == BASE
    assert state.current_seat == 0  # a capture grants an extra roll, even on a non-6
    assert state.phase == Phase.AWAITING_ROLL


def test_a_capture_sends_every_opponent_token_on_that_square_home():
    state = new_game(4)  # Red, Green, Yellow, Blue
    state = set_token(state, 0, 0, track(3))  # Red absolute 3, will land on 5
    state = set_token(state, 1, 0, track(44))  # Green  (13 + 44) % 52 = 5
    state = set_token(state, 2, 0, track(31))  # Yellow (26 + 31) % 52 = 5
    state = set_token(state, 2, 1, track(31))  # a second Yellow token on the same square
    state = apply_move(set_phase(state, Phase.AWAITING_MOVE, 2), 0)

    assert state.players[1].tokens[0] == BASE
    assert state.players[2].tokens[0] == BASE
    assert state.players[2].tokens[1] == BASE


def test_your_own_tokens_never_capture_each_other():
    state = new_game(2)
    state = set_token(state, 0, 0, track(3))
    state = set_token(state, 0, 1, track(5))
    state = apply_move(set_phase(state, Phase.AWAITING_MOVE, 2), 0)

    assert state.players[0].tokens[0] == track(5)
    assert state.players[0].tokens[1] == track(5)
    assert state.current_seat == 1  # no capture, so no extra roll


def test_no_capture_on_a_start_square():
    state = new_game(2)
    state = set_token(state, 0, 0, track(10))  # Red absolute 10
    state = set_token(state, 1, 0, track(39))  # Yellow absolute 13 (a start square)
    state = apply_move(set_phase(state, Phase.AWAITING_MOVE, 3), 0)

    assert state.players[0].tokens[0] == track(13)
    assert state.players[1].tokens[0] == track(39)


def test_no_capture_on_a_star_square():
    state = new_game(2)
    state = set_token(state, 0, 0, track(18))  # Red absolute 18
    state = set_token(state, 1, 0, track(47))  # Yellow absolute 21 (a star square)
    state = apply_move(set_phase(state, Phase.AWAITING_MOVE, 3), 0)

    assert state.players[0].tokens[0] == track(21)
    assert state.players[1].tokens[0] == track(47)


# --- winning ------------------------------------------------------------------


def test_finishing_the_last_token_wins_the_game_and_locks_it():
    state = new_game(2)
    for token in (0, 1, 2):
        state = set_token(state, 0, token, FINISHED)
    state = set_token(state, 0, 3, track(50))
    state = apply_move(set_phase(state, Phase.AWAITING_MOVE, 6), 3)

    assert state.phase == Phase.GAME_OVER
    assert state.winner == Colour.RED
    assert state.pending_die is None
    # The final board must show the winning move, not the position before it.
    assert state.players[0].tokens[3] == FINISHED
    with pytest.raises(GameOverError):
        apply_roll(state, 4)
