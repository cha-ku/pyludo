from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .engine.errors import LudoError
from .engine.state import GameState
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
        return cls(code=error.code, message=error.message)


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


class MemberView(View):
    nickname: str
    seat: int
    connected: bool


class Snapshot(BaseMessage):
    type: Literal["snapshot"] = "snapshot"
    code: str
    host_seat: int
    members: list[MemberView]
    game: GameState | None

    @classmethod
    def from_room(cls, room: Room):
        return cls(
            code=room.code,
            host_seat=room.host.seat,
            members=[MemberView.model_validate(m) for m in room.members],
            game=room.game,
        )
