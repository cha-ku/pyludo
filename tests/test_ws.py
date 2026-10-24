import time
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from helpers import FINISHED, home, set_token
from pyludo.engine.models import Phase
from pyludo.rooms import Room, RoomRegistry
from pyludo.server import create_app

# A server that forgets to send something would leave receive_json() waiting forever.
# pytest-timeout turns that hang into a failure.
pytestmark = pytest.mark.timeout(5)


@pytest.fixture
def setup():
    """Call it to get a fresh app with its own registry, one room, and a scripted die.

    The TestClient is *entered*, which runs every connection of the test on one event loop, as a
    real server does. A TestClient that isn't entered gives each connection its own loop in its own
    thread, and the turn timer started from one connection could not be stopped from another.
    """
    with ExitStack() as stack:

        def make(
            dice: list[int] | None = None, turn_seconds: float = 30.0
        ) -> tuple[TestClient, Room]:
            registry = RoomRegistry()
            room = registry.create()
            app = create_app(
                registry=registry,
                roll_die=iter(dice or []).__next__,
                turn_seconds=turn_seconds,
            )
            return stack.enter_context(TestClient(app)), room

        yield make


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


def test_an_unknown_room_gets_an_error_and_is_closed(setup):
    client, _ = setup()
    with client.websocket_connect("/ws/no-such-room") as ws:
        assert _error(ws)["code"] == "room_not_found"
        _assert_closed(ws)


def test_hello_gets_a_welcome_and_then_a_snapshot(setup):
    client, room = setup()
    with client.websocket_connect(f"/ws/{room.code}") as ws:
        welcome = _hello(ws, "Ann")
        assert welcome == {"type": "welcome", "session": room.members[0].session, "seat": 0}
        snapshot = _snapshot(ws)
        assert snapshot["code"] == room.code
        assert [m["nickname"] for m in snapshot["members"]] == ["Ann"]


def test_the_first_message_must_be_hello(setup):
    client, room = setup()
    with client.websocket_connect(f"/ws/{room.code}") as ws:
        ws.send_json({"type": "start"})
        assert _error(ws)["code"] == "invalid_message"
        _assert_closed(ws)
    assert room.members == []


def test_a_refused_join_gets_the_rooms_error_and_is_closed(setup):
    client, room = setup()
    with client.websocket_connect(f"/ws/{room.code}") as ws:
        ws.send_json({"type": "hello", "nickname": "   "})
        assert _error(ws)["code"] == "invalid_nickname"
        _assert_closed(ws)


def test_everyone_gets_a_snapshot_when_someone_joins(setup):
    client, room = setup()
    with ExitStack() as stack:
        ann = stack.enter_context(client.websocket_connect(f"/ws/{room.code}"))
        _hello(ann, "Ann")
        _snapshot(ann)
        bob = stack.enter_context(client.websocket_connect(f"/ws/{room.code}"))
        assert _hello(bob, "Bob")["seat"] == 1
        assert len(_snapshot(bob)["members"]) == 2
        assert [m["nickname"] for m in _snapshot(ann)["members"]] == ["Ann", "Bob"]


def test_a_fifth_player_is_refused(setup):
    client, room = setup()
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


def test_a_newcomer_is_refused_while_a_game_is_running(setup):
    client, room = setup()
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        late = stack.enter_context(client.websocket_connect(f"/ws/{room.code}"))
        late.send_json({"type": "hello", "nickname": "Cat"})
        assert _error(late)["code"] == "game_in_progress"
        _assert_closed(late)


# --- Playing ---------------------------------------------------------------


def test_the_host_starts_the_game_for_everyone(setup):
    client, room = setup()
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        ann.send_json({"type": "start"})
        for ws in (ann, bob):
            game = _snapshot(ws)["game"]
            assert game["phase"] == "AWAITING_ROLL"
            assert game["current_seat"] == 0


def test_an_error_goes_only_to_the_sender_and_the_connection_stays_open(setup):
    client, room = setup()
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        bob.send_json({"type": "start"})
        assert _error(bob)["code"] == "not_host"
        ann.send_json({"type": "start"})
        # If Ann had been sent Bob's error, she would read it here instead of the snapshot.
        assert _snapshot(ann)["game"] is not None
        assert _snapshot(bob)["game"] is not None


def test_a_bad_message_gets_an_error_and_the_connection_stays_open(setup):
    client, room = setup()
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        ann.send_text("this is not json")
        assert _error(ann)["code"] == "invalid_message"
        ann.send_json({"type": "hello", "nickname": "Ann"})  # hello is only for joining
        assert _error(ann)["code"] == "invalid_message"
        _start(ann, bob)  # still connected and still playing


def test_the_server_rolls_the_die_and_everyone_sees_it(setup):
    client, room = setup(dice=[6])
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        ann.send_json({"type": "roll"})
        for ws in (ann, bob):
            game = _snapshot(ws)["game"]
            assert game["phase"] == "AWAITING_MOVE"
            assert game["pending_die"] == 6


def test_a_roll_that_passes_the_turn_is_shown_to_everyone(setup):
    client, room = setup(dice=[3])
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        ann.send_json({"type": "roll"})  # a 3 with everything in base: nothing to move
        for ws in (ann, bob):
            game = _snapshot(ws)["game"]
            assert game["current_seat"] == 1
            assert game["pending_die"] is None  # the game has moved on...
            assert game["last_roll"] == {"seat": 0, "die": 3}  # ...but shows what Ann rolled


def test_a_client_cannot_choose_its_own_die(setup):
    client, room = setup(dice=[3])
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        ann.send_json({"type": "roll", "die": 6})
        assert _error(ann)["code"] == "invalid_message"
        assert room.game.phase == Phase.AWAITING_ROLL  # nothing was rolled


def test_moving_a_token(setup):
    client, room = setup(dice=[6])
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


def test_playing_out_of_turn_is_an_error(setup):
    client, room = setup(dice=[6])
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        bob.send_json({"type": "roll"})
        assert _error(bob)["code"] == "not_your_turn"


def test_each_roll_uses_the_next_die(setup):
    client, room = setup(dice=[3, 6])
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        ann.send_json({"type": "roll"})  # a 3 with everything in base: Bob's turn
        assert _snapshot(ann)["game"]["current_seat"] == 1
        _snapshot(bob)
        bob.send_json({"type": "roll"})
        assert _snapshot(bob)["game"]["pending_die"] == 6


# --- Leaving and coming back -----------------------------------------------


def test_closing_the_connection_marks_the_member_disconnected(setup):
    client, room = setup()
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


def test_reconnecting_with_the_session_regains_the_seat(setup):
    client, room = setup()
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


# --- The turn timer --------------------------------------------------------

TURN = 0.3  # seconds; the real game gives 30


def test_a_started_game_shows_the_time_left_in_the_turn(setup):
    client, room = setup(turn_seconds=TURN)
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        ann.send_json({"type": "start"})
        for ws in (ann, bob):
            assert 0 < _snapshot(ws)["game"]["seconds_left"] <= TURN


def test_when_time_runs_out_the_server_plays_the_turn(setup):
    client, room = setup(dice=[6], turn_seconds=TURN)
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        # Nobody does anything. The next snapshot comes from the timer.
        for ws in (ann, bob):
            game = _snapshot(ws)["game"]
            assert game["last_roll"] == {"seat": 0, "die": 6}
            assert game["players"][0]["tokens"][0]["kind"] == "TRACK"  # first token out of base
            assert game["current_seat"] == 0  # a 6: Ann's turn again...
            assert game["seconds_left"] > 0  # ...with a new countdown


def test_acting_starts_a_new_countdown(setup):
    client, room = setup(dice=[3], turn_seconds=1.0)
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        time.sleep(0.5)
        ann.send_json({"type": "roll"})  # nothing to move on a 3: Bob's turn
        game = _snapshot(ann)["game"]
        assert game["current_seat"] == 1
        assert game["seconds_left"] > 0.8  # Bob gets the whole turn, not what Ann left


def test_a_snapshot_mid_turn_shows_the_time_still_left(setup):
    client, room = setup(turn_seconds=1.0)
    with client.websocket_connect(f"/ws/{room.code}") as ann:
        _hello(ann, "Ann")
        _snapshot(ann)
        with client.websocket_connect(f"/ws/{room.code}") as bob:
            _hello(bob, "Bob")
            _snapshot(bob)
            _snapshot(ann)
            _start(ann, bob)
            time.sleep(0.4)
        # Bob leaving changes the room, but it doesn't give Ann more time.
        assert _snapshot(ann)["game"]["seconds_left"] < 0.7


def test_a_disconnected_player_is_played_for_when_their_time_runs_out(setup):
    client, room = setup(dice=[3], turn_seconds=TURN)
    with client.websocket_connect(f"/ws/{room.code}") as bob:
        with client.websocket_connect(f"/ws/{room.code}") as ann:
            _hello(ann, "Ann")
            _snapshot(ann)
            _hello(bob, "Bob")
            _snapshot(bob)
            _snapshot(ann)
            _start(ann, bob)
        # Ann has left, on her own turn.
        assert [m["connected"] for m in _snapshot(bob)["members"]] == [False, True]
        game = _snapshot(bob)["game"]  # her time ran out
        assert game["last_roll"] == {"seat": 0, "die": 3}
        assert game["current_seat"] == 1  # nothing to move on a 3: Bob's turn


def test_there_is_no_countdown_once_the_game_is_over(setup):
    client, room = setup(dice=[1, 6], turn_seconds=TURN)  # the server rolls before it checks
    with ExitStack() as stack:
        ann, bob = _join_two(client, room, stack)
        _start(ann, bob)
        # Ann is one step from winning: three tokens home, the last on the final home square.
        game = room.game
        for token in (1, 2, 3):
            game = set_token(game, 0, token, FINISHED)
        room.game = set_token(game, 0, 0, home(4))
        ann.send_json({"type": "roll"})
        _snapshot(ann)
        ann.send_json({"type": "move", "token": 0})
        game = _snapshot(ann)["game"]
        assert game["phase"] == "GAME_OVER"
        assert game["seconds_left"] is None
        # And the timer really is stopped: nothing else arrives, even after a turn's time.
        time.sleep(2 * TURN)
        ann.send_json({"type": "roll"})
        assert _error(ann)["code"] == "game_over"
