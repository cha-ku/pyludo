from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .board_layout import cell_for
from .engine.errors import LudoError
from .engine.models import Colour, Phase, PosKind, TokenPosition
from .engine.rules import movable_tokens
from .engine.state import PlayerState
from .rooms import Room


class InvalidMessageError(LudoError):
    code = "invalid_message"
    message = "Bad message"


class BaseMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


# --- Client message models


class Hello(BaseMessage):
    type: Literal["hello"] = "hello"
    nickname: str
    session: str | None = None


class Start(BaseMessage):
    type: Literal["start"] = "start"


class Roll(BaseMessage):
    type: Literal["roll"] = "roll"


class Move(BaseMessage):
    type: Literal["move"] = "move"
    token: int


ClientMessage = TypeAdapter(Annotated[Hello | Start | Roll | Move, Field(discriminator="type")])


# https://pydantic.dev/docs/validation/latest/concepts/unions/#discriminated-unions
def parse_client_message(text: str) -> ClientMessage:
    try:
        return ClientMessage.validate_json(text)
    except ValidationError:
        raise InvalidMessageError from None


# --- Server message models


class Error(BaseMessage):
    type: Literal["error"] = "error"
    code: str
    message: str

    @classmethod
    def from_exception(cls, error: LudoError):
        return cls(code=error.code, message=str(error))


class Welcome(BaseMessage):
    type: Literal["welcome"] = "welcome"
    session: str
    seat: int


# -- Views to help filter fields from Models

# Prevents from sending session value or other secrets to the client


class View(BaseModel):
    # frozen: View is immutable
    # from_attributes: https://github.com/pydantic/pydantic/discussions/8933 -
    #                  allows partial matching of attributes
    model_config = ConfigDict(from_attributes=True, frozen=True)


class CellView(View):
    row: int
    col: int


class TokenView(View):
    kind: PosKind
    index: int
    cell: CellView

    @classmethod
    def from_token(cls, colour: Colour, token_index: int, token: TokenPosition):
        return cls(
            kind=token.kind,
            index=token.index,
            cell=CellView.model_validate(cell_for(colour, token_index, token)),
        )


class DieRollView(View):
    seat: int
    die: int


class PlayerStateView(View):
    colour: Colour
    tokens: list[TokenView]

    @classmethod
    def from_player(cls, player: PlayerState):
        return cls(
            colour=player.colour,
            tokens=[
                TokenView.from_token(player.colour, token_index, token)
                for token_index, token in enumerate(player.tokens)
            ],
        )


class GameStateView(View):
    phase: Phase
    last_roll: DieRollView | None
    movable_tokens: list[int]
    players: list[PlayerStateView]
    current_seat: int
    pending_die: int | None
    winner: Colour | None

    @classmethod
    def from_room(cls, room: Room):
        game = room.game
        return cls(
            phase=game.phase,
            last_roll=DieRollView.model_validate(room.last_roll) if room.last_roll else None,
            movable_tokens=movable_tokens(game, game.pending_die)
            if game.phase == Phase.AWAITING_MOVE
            else [],
            players=[PlayerStateView.from_player(player) for player in game.players],
            current_seat=game.current_seat,
            pending_die=game.pending_die,
            winner=game.winner,
        )


class MemberView(View):
    nickname: str
    seat: int
    connected: bool


class Snapshot(BaseMessage):
    type: Literal["snapshot"] = "snapshot"
    code: str
    host_seat: int
    members: list[MemberView]
    game: GameStateView | None

    @classmethod
    def from_room(cls, room: Room):
        return cls(
            code=room.code,
            host_seat=room.host.seat,
            members=[MemberView.model_validate(m) for m in room.members],
            game=GameStateView.from_room(room) if room.game else None,
        )
