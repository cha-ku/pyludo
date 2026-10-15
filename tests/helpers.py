"""Test-only helpers for building game states the engine would never reach on its own.

The C++ helpers mutated the state in place. Our GameState is frozen, so these return a
*new* state built with dataclasses.replace(). They rely on two parts of the spec:
GameState.players is a tuple of PlayerState, and PlayerState.tokens is a tuple of
TokenPosition.
"""

from dataclasses import replace

from pyludo.engine.models import Phase, PosKind, TokenPosition
from pyludo.engine.state import GameState

BASE = TokenPosition(PosKind.BASE)
FINISHED = TokenPosition(PosKind.FINISHED)


def track(index: int) -> TokenPosition:
    return TokenPosition(PosKind.TRACK, index)


def home(index: int) -> TokenPosition:
    return TokenPosition(PosKind.HOME_COLUMN, index)


def set_token(state: GameState, seat: int, token: int, pos: TokenPosition) -> GameState:
    player = state.players[seat]
    tokens = player.tokens[:token] + (pos,) + player.tokens[token + 1 :]
    players = state.players[:seat] + (replace(player, tokens=tokens),) + state.players[seat + 1 :]
    return replace(state, players=players)


def set_phase(state: GameState, phase: Phase, pending_die: int | None = None) -> GameState:
    return replace(state, phase=phase, pending_die=pending_die)
