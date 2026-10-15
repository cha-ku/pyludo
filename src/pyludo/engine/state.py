from dataclasses import dataclass

from .errors import InvalidPlayerCountError
from .models import Colour, Phase, PosKind, TokenPosition
from .path import TOKENS_PER_PLAYER


@dataclass(frozen=True)
class PlayerState:
    colour: Colour
    tokens: tuple[TokenPosition, ...] = (TokenPosition(PosKind.BASE),) * TOKENS_PER_PLAYER


@dataclass(frozen=True)
class GameState:
    players: tuple[PlayerState, ...]
    current_seat: int = 0
    phase: Phase = Phase.AWAITING_ROLL
    pending_die: int | None = None
    winner: Colour | None = None

    @property
    def player_count(self) -> int:
        return len(self.players)


SEAT_COLOURS: dict[int, tuple[Colour, ...]] = {
    2: (Colour.RED, Colour.YELLOW),  # opposite corners
    3: (Colour.RED, Colour.GREEN, Colour.YELLOW),
    4: (Colour.RED, Colour.GREEN, Colour.YELLOW, Colour.BLUE),
}


def new_game(player_count: int) -> GameState:
    colours = SEAT_COLOURS.get(player_count)
    if colours is None:
        raise InvalidPlayerCountError(f"player count must be between 2 and 4, got {player_count}")
    return GameState(players=tuple(PlayerState(colour) for colour in colours))
