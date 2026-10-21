import json
from dataclasses import replace

import pytest

from helpers import FINISHED, home, set_phase, set_token, track
from pyludo.engine.errors import LudoError
from pyludo.engine.models import Colour, Phase
from pyludo.protocol import (
    Error,
    Hello,
    InvalidMessageError,
    Move,
    Roll,
    Snapshot,
    Start,
    Welcome,
    parse_client_message,
)
from pyludo.rooms import Room, RoomFullError


def _room_with(*nicknames: str) -> Room:
    room = Room("abc")
    for nickname in nicknames:
        room.join(nickname)
    return room


def _snapshot(room: Room) -> dict:
    """The snapshot exactly as a client will receive it: JSON text, parsed."""
    return json.loads(Snapshot.from_room(room).model_dump_json())


def _started_with_two() -> Room:
    """Ann (seat 0, Red) and Bob (seat 1, Yellow) in a new game."""
    room = _room_with("Ann", "Bob")
    room.start(room.members[0].session)
    return room


def _in_base(*cells: tuple[int, int]) -> list[dict]:
    return [{"kind": "BASE", "index": 0, "cell": {"row": r, "col": c}} for r, c in cells]


# --- Client -> server: parsing ---------------------------------------------


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"type": "hello", "nickname": "Ann"}', Hello(nickname="Ann")),
        (
            '{"type": "hello", "nickname": "Ann", "session": "s3cret"}',
            Hello(nickname="Ann", session="s3cret"),
        ),
        ('{"type": "start"}', Start()),
        ('{"type": "roll"}', Roll()),
        ('{"type": "move", "token": 2}', Move(token=2)),
    ],
)  # fmt: skip
def test_valid_messages_parse_into_their_model(text, message):
    assert parse_client_message(text) == message


def test_a_new_hello_has_no_session():
    assert parse_client_message('{"type": "hello", "nickname": "Ann"}').session is None


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        "{}",  # no type
        '{"type": "fly"}',  # unknown type
        '{"type": "hello"}',  # no nickname
        '{"type": "hello", "nickname": 7}',  # nickname must be text
        '{"type": "move"}',  # which token?
        '{"type": "move", "token": "2"}',  # strict: no quietly turning text into numbers
        '{"type": "move", "token": true}',  # ...or booleans
        '{"type": "roll", "die": 6}',  # extra fields are refused: the server rolls the die
    ],
)
def test_anything_else_is_an_invalid_message(text):
    with pytest.raises(InvalidMessageError):
        parse_client_message(text)


def test_invalid_message_is_a_ludo_error_with_a_code():
    assert issubclass(InvalidMessageError, LudoError)
    assert InvalidMessageError.code == "invalid_message"
    assert InvalidMessageError.message != LudoError.message


# --- Server -> client: welcome and error -----------------------------------


def test_welcome_tells_a_member_their_session_and_seat():
    welcome = Welcome(session="s3cret", seat=1)
    assert json.loads(welcome.model_dump_json()) == {
        "type": "welcome",
        "session": "s3cret",
        "seat": 1,
    }


def test_an_error_message_comes_from_a_ludo_error():
    error = Error.from_exception(RoomFullError())
    assert json.loads(error.model_dump_json()) == {
        "type": "error",
        "code": "room_full",
        "message": RoomFullError.message,
    }


def test_an_error_message_keeps_a_custom_message():
    error = Error.from_exception(LudoError("token 3 is still in base"))
    assert error.message == "token 3 is still in base"


# --- Server -> client: snapshot --------------------------------------------


def test_a_lobby_snapshot_lists_the_members_and_has_no_game():
    room = _room_with("Ann", "Bob")
    room.disconnect(room.members[1].session)
    assert _snapshot(room) == {
        "type": "snapshot",
        "code": "abc",
        "host_seat": 0,
        "members": [
            {"nickname": "Ann", "seat": 0, "connected": True},
            {"nickname": "Bob", "seat": 1, "connected": False},
        ],
        "game": None,
    }


def test_a_snapshot_never_contains_a_session():
    room = _room_with("Ann", "Bob")
    room.start(room.members[0].session)
    text = Snapshot.from_room(room).model_dump_json()
    for member in room.members:
        assert member.session not in text  # everyone in the room receives the snapshot


def test_a_snapshot_of_a_new_game():
    room = _started_with_two()
    assert _snapshot(room)["game"] == {
        "phase": "AWAITING_ROLL",
        "current_seat": 0,
        "pending_die": None,
        "winner": None,
        "last_roll": None,
        "movable_tokens": [],
        "players": [
            {"colour": "red", "tokens": _in_base((1, 1), (1, 4), (4, 1), (4, 4))},
            {"colour": "yellow", "tokens": _in_base((10, 10), (10, 13), (13, 10), (13, 13))},
        ],
    }


def test_tokens_are_sent_as_engine_positions_with_their_board_cells():
    room = _started_with_two()
    room.game = set_token(room.game, 0, 0, track(5))
    room.game = set_token(room.game, 0, 1, home(2))
    room.game = set_token(room.game, 1, 0, track(0))
    room.game = set_token(room.game, 1, 2, FINISHED)
    red, yellow = _snapshot(room)["game"]["players"]
    assert red["tokens"][0] == {"kind": "TRACK", "index": 5, "cell": {"row": 5, "col": 6}}
    assert red["tokens"][1] == {"kind": "HOME_COLUMN", "index": 2, "cell": {"row": 7, "col": 3}}
    # The same track index is a different square for each colour: Yellow starts on the far side.
    assert yellow["tokens"][0] == {"kind": "TRACK", "index": 0, "cell": {"row": 8, "col": 13}}
    assert yellow["tokens"][2] == {"kind": "FINISHED", "index": 0, "cell": {"row": 7, "col": 7}}


def test_a_snapshot_after_a_roll_shows_the_die_and_the_movable_tokens():
    room = _started_with_two()
    room.roll(room.members[0].session, 6)
    game = _snapshot(room)["game"]
    assert game["phase"] == "AWAITING_MOVE"
    assert game["pending_die"] == 6
    assert game["last_roll"] == {"seat": 0, "die": 6}
    assert game["movable_tokens"] == [0, 1, 2, 3]  # a 6 lets any token out of base


def test_only_tokens_that_can_move_are_movable():
    room = _started_with_two()
    room.game = set_token(room.game, 0, 2, track(5))
    room.roll(room.members[0].session, 2)  # the others are in base and need a 6
    assert _snapshot(room)["game"]["movable_tokens"] == [2]


def test_a_roll_that_passes_the_turn_still_shows_the_die():
    room = _started_with_two()
    room.roll(room.members[0].session, 3)
    game = _snapshot(room)["game"]
    assert game["current_seat"] == 1
    assert game["pending_die"] is None
    assert game["last_roll"] == {"seat": 0, "die": 3}
    assert game["movable_tokens"] == []


def test_a_finished_game_shows_the_winner():
    room = _started_with_two()
    room.game = replace(set_phase(room.game, Phase.GAME_OVER), winner=Colour.YELLOW)
    game = _snapshot(room)["game"]
    assert game["phase"] == "GAME_OVER"
    assert game["winner"] == "yellow"
