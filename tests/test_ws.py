from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from pyludo.engine.models import Phase
from pyludo.rooms import Room, RoomRegistry
from pyludo.server import create_app

# A server that forgets to send something would leave receive_json() waiting forever.
# pytest-timeout turns that hang into a failure.
pytestmark = pytest.mark.timeout(5)


def _setup(dice: list[int] | None = None) -> tuple[TestClient, Room]:
    """A fresh app with its own registry, one room, and a scripted die."""
    registry = RoomRegistry()
    room = registry.create()
    app = create_app(registry=registry, roll_die=iter(dice or []).__next__)
    return TestClient(app), room


def _hello(ws, nickname: str, session: str | None = None) -> dict:
    """Send hello and return the welcome. The snapshot that follows is left for the caller."""
    message = {"type": "hello", "nickname": nickname}
    if session is not None:
        message["session"] = session
    ws.send_json(message)
    welcome = ws.receive_json()
    assert welcome["type"] == "welcome", welcome
    return welcome


def _snapshot(ws) -> dict:
    message = ws.receive_json()
    assert message["type"] == "snapshot", message
    return message


def _error(ws) -> dict:
    message = ws.receive_json()
    assert message["type"] == "error", message
    return message


def _assert_closed(ws) -> None:
    with pytest.raises(WebSocketDisconnect):
        ws.receive_json()


def _join_two(client: TestClient, room: Room, stack: ExitStack):
    """Ann (host, seat 0) and Bob (seat 1) connected, with every join message drained."""
    ann = stack.enter_context(client.websocket_connect(f"/ws/{room.code}"))
    _hello(ann, "Ann")
    _snapshot(ann)
    bob = stack.enter_context(client.websocket_connect(f"/ws/{room.code}"))
    _hello(bob, "Bob")
    _snapshot(bob)
    _snapshot(ann)  # Ann hears that Bob joined
    return ann, bob


def _start(ann, bob) -> None:
    ann.send_json({"type": "start"})
    _snapshot(ann)
    _snapshot(bob)


# --- Connecting and hello --------------------------------------------------


def test_an_unknown_room_gets_an_error_and_is_closed():
    client, _ = _setup()
    with client.websocket_connect("/ws/no-such-room") as ws:
        assert _error(ws)["code"] == "room_not_found"
        _assert_closed(ws)


def test_hello_gets_a_welcome_and_then_a_snapshot():
    client, room = _setup()
    with client.websocket_connect(f"/ws/{room.code}") as ws:
        welcome = _hello(ws, "Ann")
        assert welcome == {"type": "welcome", "session": room.members[0].session, "seat": 0}
        snapshot = _snapshot(ws)
        assert snapshot["code"] == room.code
        assert [m["nickname"] for m in snapshot["members"]] == ["Ann"]


def test_the_first_message_must_be_hello():
    client, room = _setup()
    with client.websocket_connect(f"/ws/{room.code}") as ws:
        ws.send_json({"type": "start"})
        assert _error(ws)["code"] == "invalid_message"
        _assert_closed(ws)
    assert room.members == []


def test_a_refused_join_gets_the_rooms_error_and_is_closed():
    client, room = _setup()
    with client.websocket_connect(f"/ws/{room.code}") as ws:
        ws.send_json({"type": "hello", "nickname": "   "})
        assert _error(ws)["code"] == "invalid_nickname"
        _assert_closed(ws)


def test_everyone_gets_a_snapshot_when_someone_joins():
    client, room = _setup()
    with ExitStack() as stack:
        ann = stack.enter_context(client.websocket_connect(f"/ws/{room.code}"))
        _hello(ann, "Ann")
        _snapshot(ann)
        bob = stack.enter_context(client.websocket_connect(f"/ws/{room.code}"))
        assert _hello(bob, "Bob")["seat"] == 1
        assert len(_snapshot(bob)["members"]) == 2
        assert [m["nickname"] for m in _snapshot(ann)["members"]] == ["Ann", "Bob"]


def test_a_fifth_player_is_refused():
    client, room = _setup()
    with ExitStack() as stack:
        sockets = []
        for nickname in ["Ann", "Bob", "Cat", "Dan"]:
            ws = stack.enter_context(client.websocket_connect(f"/ws/{room.code}"))
            _hello(ws, nickname)
            sockets.append(ws)
            for each in sockets:
                _snapshot(each)
        late = stack.enter_context(client.websocket_connect(f"/ws/{room.code}"))
        late.send_json({"type": "hello", "nickname": "Eve"})
        assert _error(late)["code"] == "room_full"
        _assert_closed(late)


def test_a_newcomer_is_refused_while_a_game_is_running():
    client, room = _setup()
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        late = stack.enter_context(client.websocket_connect(f"/ws/{room.code}"))
        late.send_json({"type": "hello", "nickname": "Cat"})
        assert _error(late)["code"] == "game_in_progress"
        _assert_closed(late)


# --- Playing ---------------------------------------------------------------


def test_the_host_starts_the_game_for_everyone():
    client, room = _setup()
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        ann.send_json({"type": "start"})
        for ws in (ann, bob):
            game = _snapshot(ws)["game"]
            assert game["phase"] == "AWAITING_ROLL"
            assert game["current_seat"] == 0


def test_an_error_goes_only_to_the_sender_and_the_connection_stays_open():
    client, room = _setup()
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        bob.send_json({"type": "start"})
        assert _error(bob)["code"] == "not_host"
        ann.send_json({"type": "start"})
        # If Ann had been sent Bob's error, she would read it here instead of the snapshot.
        assert _snapshot(ann)["game"] is not None
        assert _snapshot(bob)["game"] is not None


def test_a_bad_message_gets_an_error_and_the_connection_stays_open():
    client, room = _setup()
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        ann.send_text("this is not json")
        assert _error(ann)["code"] == "invalid_message"
        ann.send_json({"type": "hello", "nickname": "Ann"})  # hello is only for joining
        assert _error(ann)["code"] == "invalid_message"
        _start(ann, bob)  # still connected and still playing


def test_the_server_rolls_the_die_and_everyone_sees_it():
    client, room = _setup(dice=[6])
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        ann.send_json({"type": "roll"})
        for ws in (ann, bob):
            game = _snapshot(ws)["game"]
            assert game["phase"] == "AWAITING_MOVE"
            assert game["pending_die"] == 6


def test_a_roll_that_passes_the_turn_is_shown_to_everyone():
    client, room = _setup(dice=[3])
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        ann.send_json({"type": "roll"})  # a 3 with everything in base: nothing to move
        for ws in (ann, bob):
            game = _snapshot(ws)["game"]
            assert game["current_seat"] == 1
            assert game["pending_die"] is None  # the game has moved on...
            assert game["last_roll"] == {"seat": 0, "die": 3}  # ...but shows what Ann rolled


def test_a_client_cannot_choose_its_own_die():
    client, room = _setup(dice=[3])
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        ann.send_json({"type": "roll", "die": 6})
        assert _error(ann)["code"] == "invalid_message"
        assert room.game.phase == Phase.AWAITING_ROLL  # nothing was rolled


def test_moving_a_token():
    client, room = _setup(dice=[6])
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        ann.send_json({"type": "roll"})
        _snapshot(ann)
        _snapshot(bob)
        ann.send_json({"type": "move", "token": 0})
        for ws in (ann, bob):
            snapshot = _snapshot(ws)
            token = snapshot["game"]["players"][0]["tokens"][0]
            assert token == {"kind": "TRACK", "index": 0, "cell": {"row": 6, "col": 1}}
            assert snapshot["game"]["current_seat"] == 0  # rolled a 6: Ann goes again


def test_playing_out_of_turn_is_an_error():
    client, room = _setup(dice=[6])
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        bob.send_json({"type": "roll"})
        assert _error(bob)["code"] == "not_your_turn"


def test_each_roll_uses_the_next_die():
    client, room = _setup(dice=[3, 6])
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        ann.send_json({"type": "roll"})  # a 3 with everything in base: Bob's turn
        assert _snapshot(ann)["game"]["current_seat"] == 1
        _snapshot(bob)
        bob.send_json({"type": "roll"})
        assert _snapshot(bob)["game"]["pending_die"] == 6


# --- Leaving and coming back -----------------------------------------------


def test_closing_the_connection_marks_the_member_disconnected():
    client, room = _setup()
    with client.websocket_connect(f"/ws/{room.code}") as ann:
        _hello(ann, "Ann")
        _snapshot(ann)
        with client.websocket_connect(f"/ws/{room.code}") as bob:
            _hello(bob, "Bob")
            _snapshot(bob)
            _snapshot(ann)
        # Bob's `with` block has closed his socket.
        members = _snapshot(ann)["members"]
        assert [m["connected"] for m in members] == [True, False]
        assert not room.members[1].connected


def test_reconnecting_with_the_session_regains_the_seat():
    client, room = _setup()
    with client.websocket_connect(f"/ws/{room.code}") as ann:
        _hello(ann, "Ann")
        _snapshot(ann)
        with client.websocket_connect(f"/ws/{room.code}") as bob:
            session = _hello(bob, "Bob")["session"]
            _snapshot(bob)
            _snapshot(ann)
        _snapshot(ann)  # Bob left

        with client.websocket_connect(f"/ws/{room.code}") as bob_again:
            welcome = _hello(bob_again, "Bob", session=session)
            assert welcome == {"type": "welcome", "session": session, "seat": 1}
            _snapshot(bob_again)
            members = _snapshot(ann)["members"]
            assert [m["connected"] for m in members] == [True, True]
            assert len(room.members) == 2
