import secrets
from collections.abc import Callable
from dataclasses import dataclass, field

from .engine.errors import LudoError
from .engine.models import Colour, Phase
from .engine.rules import apply_move, apply_roll
from .engine.state import GameState, new_game

MIN_NICKNAME_LEN = 1
MAX_NICKNAME_LEN = 20


def _default_code_generator() -> str:
    return secrets.token_urlsafe(8)


class RoomError(LudoError):
    code = "room_error"
    message = "room error"


class GameInProgressError(RoomError):
    code = "game_in_progress"
    message = "game already in progress"


class GameNotStartedError(RoomError):
    code = "game_not_started"
    message = "game has not started yet"


class InvalidMemberError(LudoError):
    code = "invalid_member"
    message = "member is not valid"


class InvalidNicknameError(RoomError):
    code = "invalid_nickname"
    message = "nickname is invalid"


class NotHostError(RoomError):
    code = "not_host"
    message = "this action can only be done by the host"


class NotYourTurnError(RoomError):
    code = "not_your_turn"
    message = "it is not your turn"


class UnknownSessionError(RoomError):
    code = "unknown_session"
    message = "could not find a session"


class RoomFullError(RoomError):
    code = "room_full"
    message = "Room is currently full"


class RoomNotFoundError(RoomError):
    code = "room_not_found"
    message = "no room with that code"


@dataclass(frozen=True)
class DieRoll:
    seat: int
    die: int


@dataclass
class Member:
    nickname: str
    session: str
    seat: int
    connected: bool = True


@dataclass
class Room:
    code: str
    host: Member | None = None
    game: GameState | None = None
    members: list[Member] = field(default_factory=list)
    last_roll: DieRoll | None = None

    @property
    def is_empty(self) -> bool:
        return all(not member.connected for member in self.members)

    def join(self, nickname: str, session: str | None = None) -> Member:
        nickname = nickname.strip()
        if not MIN_NICKNAME_LEN <= len(nickname) <= MAX_NICKNAME_LEN:
            raise InvalidNicknameError()
        if session:
            for member in self.members:
                if member.session == session:
                    # might have a new nick
                    member.nickname = nickname
                    member.connected = True
                    return member
        if len(self.members) == 4:
            raise RoomFullError()
        if self.game and self.game.phase != Phase.GAME_OVER:
            raise GameInProgressError()
        new_member = Member(nickname, secrets.token_urlsafe(16), len(self.members))
        self.members.append(new_member)
        if self.host is None:
            self.host = new_member
        return new_member

    def _member_with_session(self, session: str) -> Member:
        member = next(
            iter(
                m
                for m in self.members
                if secrets.compare_digest(m.session.encode(), session.encode())
            ),
            None,
        )
        if member is None:
            raise UnknownSessionError()
        return member

    def start(self, session: str):
        if self.game is not None and self.game.phase != Phase.GAME_OVER:
            raise GameInProgressError()
        if self._member_with_session(session) != self.host:
            raise NotHostError()
        self.game = new_game(len(self.members))
        self.last_roll = None

    def roll(self, session: str, die: int) -> None:
        if self.game is None:
            raise GameNotStartedError()
        member = self._member_with_session(session)
        if member.seat != self.game.current_seat:
            raise NotYourTurnError()
        self.game = apply_roll(self.game, die)
        self.last_roll = DieRoll(member.seat, die)

    def move(self, session: str, token_index: int) -> None:
        if self.game is None:
            raise GameNotStartedError()
        member = self._member_with_session(session)
        if member.seat != self.game.current_seat:
            raise NotYourTurnError()
        self.game = apply_move(self.game, token_index)

    def disconnect(self, session: str) -> None:
        member = self._member_with_session(session)
        member.connected = False

    def colour_of(self, member: Member) -> Colour | None:
        if self.game is None or self.game.player_count <= member.seat:
            return None
        return self.game.players[member.seat].colour


class RoomRegistry:
    def __init__(self, make_code: Callable[[], str] = _default_code_generator) -> None:
        self._rooms: dict[str, Room] = {}
        self._make_code = make_code

    def __contains__(self, code: str) -> bool:
        return code in self._rooms

    def __len__(self) -> int:
        return len(self._rooms)

    def get(self, code: str) -> Room:
        try:
            return self._rooms[code]
        except KeyError:
            raise RoomNotFoundError() from None

    def create(self) -> Room:
        code = self._make_code()
        while code in self._rooms:
            code = self._make_code()
        self._rooms[code] = Room(code)
        return self.get(code)

    def remove_empty_rooms(self) -> list[str]:
        removed_rooms = []
        for code, room in self._rooms.items():
            if room.is_empty:
                removed_rooms.append(code)
        self._rooms = {
            code: room for code, room in self._rooms.items() if code not in removed_rooms
        }
        return removed_rooms
