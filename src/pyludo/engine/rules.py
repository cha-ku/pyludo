from dataclasses import replace

from .errors import (
    DieOutOfRangeError,
    GameOverError,
    IllegalMoveError,
    InvalidTokenIndexError,
    NotAwaitingMoveError,
    NotAwaitingRollError,
)
from .models import Colour, Phase, PosKind, TokenPosition
from .path import (
    FINISHED_PROGRESS,
    TOKENS_PER_PLAYER,
    absolute_of,
    is_safe_absolute,
    position_from_progress,
    progress_of,
)
from .state import GameState, PlayerState


def movable_tokens(state: GameState, die: int) -> list[int]:
    if state.phase == Phase.GAME_OVER:
        return []
    current_player_state: PlayerState = state.players[state.current_seat]
    valid_moves = []
    for idx, token in enumerate(current_player_state.tokens):
        if progress_of(token) is None:  # BASE
            if die == 6:
                valid_moves.append(idx)
        elif progress_of(token) + die <= FINISHED_PROGRESS:
            valid_moves.append(idx)
    return valid_moves


def _next_seat(state: GameState) -> int:
    return (state.current_seat + 1) % state.player_count


def apply_roll(state: GameState, die: int) -> GameState:
    if state.phase == Phase.GAME_OVER:
        raise GameOverError()
    if state.phase != Phase.AWAITING_ROLL:
        raise NotAwaitingRollError()
    if not 1 <= die <= 6:
        raise DieOutOfRangeError(f"die must be between 1 and 6, got {die}.")
    valid_tokens = movable_tokens(state, die)
    if not valid_tokens:
        return replace(
            state, current_seat=_next_seat(state), phase=Phase.AWAITING_ROLL, pending_die=None
        )
    return replace(state, phase=Phase.AWAITING_MOVE, pending_die=die)


def _is_on(pos: TokenPosition, colour: Colour, square: int) -> bool:
    return pos.kind == PosKind.TRACK and absolute_of(colour, pos.index) == square


def apply_move(state: GameState, token: int) -> GameState:
    if state.phase == Phase.GAME_OVER:
        raise GameOverError()
    if state.phase != Phase.AWAITING_MOVE:
        raise NotAwaitingMoveError("cannot apply move when not awaiting move")
    if not 0 <= token < TOKENS_PER_PLAYER:
        raise InvalidTokenIndexError(
            f"token index should be between 0 and {TOKENS_PER_PLAYER},\
                got {token}"
        )
    die = state.pending_die
    if die is None or not 1 <= die <= 6:
        raise DieOutOfRangeError(f"die must be between 1 and 6, got {die}")
    valid_tokens = movable_tokens(state, die)
    if token not in valid_tokens:
        raise IllegalMoveError()

    player = state.players[state.current_seat]
    old_token = player.tokens[token]
    old_token_pos = progress_of(old_token)
    if old_token_pos is None:
        new_token_pos = TokenPosition(PosKind.TRACK, 0)
    else:
        new_token_pos = position_from_progress(old_token_pos + die)

    current_finished = new_token_pos.kind == PosKind.FINISHED
    new_tokens = player.tokens[:token] + (new_token_pos,) + player.tokens[token + 1 :]

    mover = replace(player, tokens=new_tokens)

    players: list[PlayerState] = list(state.players)
    players[state.current_seat] = mover

    # Check if all mover tokens have FINISHED
    if all(t.kind == PosKind.FINISHED for t in mover.tokens):
        return replace(
            state,
            players=tuple(players),
            phase=Phase.GAME_OVER,
            pending_die=None,
            winner=mover.colour,
        )

    captured = False
    if new_token_pos.kind == PosKind.TRACK:
        square = absolute_of(mover.colour, new_token_pos.index)
        if not is_safe_absolute(square):
            for seat, opponent in enumerate(players):
                if seat == state.current_seat:
                    continue
                updated_tokens = tuple(
                    TokenPosition(PosKind.BASE) if _is_on(pos, opponent.colour, square) else pos
                    for pos in opponent.tokens
                )
                if opponent.tokens != updated_tokens:
                    captured = True
                    players[seat] = replace(opponent, tokens=updated_tokens)

    state = replace(state, players=tuple(players), phase=Phase.AWAITING_ROLL, pending_die=None)

    if captured or die == 6 or current_finished:
        return state
    return replace(state, current_seat=_next_seat(state))
