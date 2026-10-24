import string

import pytest

from helpers import FINISHED, set_phase, set_token, track
from pyludo.engine.errors import (
    IllegalMoveError,
    InvalidPlayerCountError,
    LudoError,
    NotAwaitingRollError,
)
from pyludo.engine.models import Colour, Phase
from pyludo.rooms import (
    DieRoll,
    GameInProgressError,
    GameNotStartedError,
    InvalidNicknameError,
    Member,
    NotHostError,
    NotYourTurnError,
    Room,
    RoomError,
    RoomFullError,
    RoomNotFoundError,
    RoomRegistry,
    UnknownSessionError,
)

URL_SAFE = set(string.ascii_letters + string.digits + "-_")


def _room_with(n: int) -> tuple[Room, list[Member]]:
    room = Room("test")
    members = [room.join(f"p{i}") for i in range(n)]
    return room, members


def _started(n: int) -> tuple[Room, list[Member]]:
    room, members = _room_with(n)
    room.start(members[0].session)
    return room, members


def _finish_game(room: Room) -> None:
    room.game = set_phase(room.game, Phase.GAME_OVER)


# --- Errors ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (RoomNotFoundError, "room_not_found"),
        (RoomFullError, "room_full"),
        (UnknownSessionError, "unknown_session"),
        (InvalidNicknameError, "invalid_nickname"),
        (NotHostError, "not_host"),
        (GameInProgressError, "game_in_progress"),
        (GameNotStartedError, "game_not_started"),
        (NotYourTurnError, "not_your_turn"),
    ],
)
def test_room_errors_are_ludo_errors_with_a_code(error, code):
    assert issubclass(error, RoomError)
    assert issubclass(error, LudoError)  # one `except LudoError` in M4 catches everything
    assert error.code == code
    assert error.message != LudoError.message  # a sentence a person can read, not just "error"


def test_every_room_error_says_something_different():
    errors = [
        RoomNotFoundError,
        RoomFullError,
        UnknownSessionError,
        InvalidNicknameError,
        NotHostError,
        GameInProgressError,
        GameNotStartedError,
        NotYourTurnError,
    ]
    assert len({error.message for error in errors}) == len(errors)


# --- Joining ---------------------------------------------------------------


def test_a_new_room_is_empty_with_no_game():
    room = Room("abc")
    assert room.code == "abc"
    assert room.host is None
    assert room.game is None
    assert room.members == []
    assert room.is_empty


def test_joining_returns_a_connected_member_with_a_secret_session():
    room = Room("abc")
    member = room.join("Ann")
    assert member.nickname == "Ann"
    assert member.connected
    assert len(member.session) >= 20
    assert set(member.session) <= URL_SAFE


def test_every_member_gets_a_different_session():
    room, members = _room_with(4)
    assert len({m.session for m in members}) == 4


def test_the_first_four_joiners_are_seated_in_join_order():
    room, members = _room_with(4)
    assert [m.seat for m in members] == [0, 1, 2, 3]
    assert room.members == members


def test_a_fifth_joiner_is_refused():
    room, members = _room_with(4)
    with pytest.raises(RoomFullError):
        room.join("late")
    assert room.members == members  # nothing half-added


def test_the_host_is_the_first_member():
    room, (ann, bob) = _room_with(2)
    assert room.host is ann


def test_a_newcomer_cannot_join_while_a_game_is_in_progress():
    room, members = _started(2)
    with pytest.raises(GameInProgressError):
        room.join("late")
    assert room.members == members


def test_a_newcomer_can_join_between_games():
    room, _ = _started(2)
    _finish_game(room)
    assert room.join("Cat").seat == 2


def test_nicknames_are_stripped():
    assert Room("abc").join("  Ann \n").nickname == "Ann"


@pytest.mark.parametrize("nickname", ["", "   ", "x" * 21])
def test_invalid_nicknames_are_rejected(nickname):
    room = Room("abc")
    with pytest.raises(InvalidNicknameError):
        room.join(nickname)
    assert room.members == []  # nothing half-added


def test_a_twenty_character_nickname_is_fine():
    assert Room("abc").join("x" * 20).nickname == "x" * 20


# --- Rejoining, disconnecting, emptiness -----------------------------------


def test_rejoining_with_a_known_session_returns_the_same_member_in_the_same_seat():
    room, (ann, bob) = _room_with(2)
    room.disconnect(bob.session)
    again = room.join("Bobby", session=bob.session)
    assert again is bob
    assert again.seat == 1
    assert again.connected
    assert again.nickname == "Bobby"  # renaming on rejoin is allowed
    assert len(room.members) == 2


def test_a_player_keeps_their_seat_when_rejoining_mid_game():
    room, (ann, bob) = _started(2)
    room.disconnect(ann.session)
    assert room.join("Ann", session=ann.session).seat == 0


def test_rejoining_works_even_when_the_room_is_full():
    room, members = _room_with(4)
    room.disconnect(members[3].session)
    assert room.join("p3", session=members[3].session) is members[3]


def test_rejoining_still_validates_the_nickname():
    room, (ann, _) = _room_with(2)
    with pytest.raises(InvalidNicknameError):
        room.join("", session=ann.session)


def test_an_unknown_session_is_treated_as_a_fresh_join():
    room, _ = _room_with(1)
    newcomer = room.join("Cat", session="stale-session-from-before-a-restart")
    assert newcomer.session != "stale-session-from-before-a-restart"
    assert newcomer.seat == 1


def test_an_unknown_session_follows_the_rules_for_newcomers():
    room, _ = _started(2)
    with pytest.raises(GameInProgressError):
        room.join("Cat", session="stale-session-from-before-a-restart")


def test_disconnecting_keeps_the_seat():
    room, (ann, bob) = _room_with(2)
    room.disconnect(bob.session)
    assert not bob.connected
    assert bob.seat == 1
    assert room.members == [ann, bob]


def test_disconnecting_an_unknown_session_is_an_error():
    room, _ = _room_with(1)
    with pytest.raises(UnknownSessionError):
        room.disconnect("nope")


def test_a_room_is_empty_when_nobody_is_connected():
    room, (ann, bob) = _room_with(2)
    assert not room.is_empty
    room.disconnect(ann.session)
    assert not room.is_empty
    room.disconnect(bob.session)
    assert room.is_empty


# --- Starting and playing again --------------------------------------------


def test_the_host_starts_a_game_for_the_seated_players():
    room, members = _started(3)
    assert room.game is not None
    assert room.game.player_count == 3
    assert room.game.phase == Phase.AWAITING_ROLL
    assert room.game.current_seat == 0


def test_only_the_host_can_start():
    room, (ann, bob) = _room_with(2)
    with pytest.raises(NotHostError):
        room.start(bob.session)
    assert room.game is None


def test_starting_with_an_unknown_session_is_an_error():
    room, _ = _room_with(2)
    with pytest.raises(UnknownSessionError):
        room.start("nope")


def test_one_player_is_not_enough():
    room, (ann,) = _room_with(1)
    with pytest.raises(InvalidPlayerCountError):  # the engine's error, not a new one
        room.start(ann.session)
    assert room.game is None


def test_starting_twice_is_an_error():
    room, (ann, _) = _started(2)
    game = room.game
    with pytest.raises(GameInProgressError):
        room.start(ann.session)
    assert room.game is game


def test_play_again_is_start_after_the_game_is_over():
    room, (ann, _) = _started(2)
    _finish_game(room)
    room.start(ann.session)
    assert room.game.phase == Phase.AWAITING_ROLL
    assert room.game.winner is None


def test_play_again_includes_people_who_joined_between_games():
    room, (ann, bob) = _started(2)
    _finish_game(room)
    cat = room.join("Cat")
    room.start(ann.session)
    assert room.game.player_count == 3
    assert room.members == [ann, bob, cat]


# --- Rolling and moving ----------------------------------------------------


def test_rolling_or_moving_before_a_game_is_an_error():
    room, (ann, _) = _room_with(2)
    with pytest.raises(GameNotStartedError):
        room.roll(ann.session, 6)
    with pytest.raises(GameNotStartedError):
        room.move(ann.session, 0)


def test_the_current_player_rolls_and_moves():
    room, (ann, _) = _started(2)
    room.roll(ann.session, 6)
    assert room.game.phase == Phase.AWAITING_MOVE
    room.move(ann.session, 0)
    assert room.game.players[0].tokens[0] == track(0)


def test_a_roll_with_no_move_passes_the_turn_to_the_next_seat():
    room, (ann, bob) = _started(2)
    room.roll(ann.session, 3)
    assert room.game.current_seat == 1
    room.roll(bob.session, 3)  # now it's Bob's turn
    assert room.game.current_seat == 0


def test_a_roll_never_moves_a_token_by_itself():
    room, (ann, _) = _started(2)
    room.game = set_token(room.game, 0, 0, track(5))
    room.roll(ann.session, 2)  # exactly one token can move: still Ann's choice to move it
    assert room.game.phase == Phase.AWAITING_MOVE
    assert room.game.players[0].tokens[0] == track(5)


def test_only_the_current_player_may_roll_or_move():
    room, (ann, bob) = _started(2)
    with pytest.raises(NotYourTurnError):
        room.roll(bob.session, 6)
    room.roll(ann.session, 6)
    with pytest.raises(NotYourTurnError):
        room.move(bob.session, 0)


def test_acting_with_an_unknown_session_is_an_error():
    room, _ = _started(2)
    with pytest.raises(UnknownSessionError):
        room.roll("nope", 6)
    with pytest.raises(UnknownSessionError):
        room.move("nope", 0)


def test_engine_errors_pass_through_and_leave_the_game_unchanged():
    room, (ann, _) = _started(2)
    room.game = set_token(room.game, 0, 0, FINISHED)
    room.roll(ann.session, 6)
    game = room.game
    with pytest.raises(NotAwaitingRollError):
        room.roll(ann.session, 6)
    with pytest.raises(IllegalMoveError):
        room.move(ann.session, 0)  # a finished token can't move
    assert room.game is game


# --- The last roll ---------------------------------------------------------


def test_a_new_room_has_no_last_roll():
    assert Room("abc").last_roll is None


def test_a_roll_is_remembered_even_when_it_passes_the_turn():
    room, (ann, _) = _started(2)
    room.roll(ann.session, 3)  # nothing can move: the turn passes and the game forgets the die
    assert room.game.pending_die is None
    assert room.last_roll == DieRoll(seat=0, die=3)


def test_the_last_roll_is_kept_after_the_move():
    room, (ann, _) = _started(2)
    room.roll(ann.session, 6)
    room.move(ann.session, 0)
    assert room.last_roll == DieRoll(seat=0, die=6)


def test_a_refused_roll_is_not_remembered():
    room, (ann, bob) = _started(2)
    room.roll(ann.session, 6)
    with pytest.raises(NotYourTurnError):
        room.roll(bob.session, 4)
    with pytest.raises(NotAwaitingRollError):
        room.roll(ann.session, 5)  # Ann must move first
    assert room.last_roll == DieRoll(seat=0, die=6)


def test_starting_a_game_clears_the_last_roll():
    room, (ann, _) = _started(2)
    room.roll(ann.session, 3)
    _finish_game(room)
    room.start(ann.session)
    assert room.last_roll is None


# --- Running out of time ---------------------------------------------------
# The server calls time_out when the current player's time is up. It plays the turn the way the
# player could have: roll if they haven't yet, then move the first token that can move.


def test_running_out_of_time_rolls_and_moves_the_first_token_that_can_move():
    room, _ = _started(2)
    room.time_out(6)
    assert room.last_roll == DieRoll(seat=0, die=6)
    assert room.game.players[0].tokens[0] == track(0)  # any token could leave base: token 0 does
    assert room.game.current_seat == 0  # a 6: Ann rolls again
    assert room.game.phase == Phase.AWAITING_ROLL


def test_running_out_of_time_after_rolling_only_moves():
    room, (ann, _) = _started(2)
    room.roll(ann.session, 6)
    room.time_out(4)  # the 4 isn't used: Ann had already rolled
    assert room.last_roll == DieRoll(seat=0, die=6)
    assert room.game.players[0].tokens[0] == track(0)


def test_the_first_token_that_can_move_is_the_lowest_numbered():
    room, _ = _started(2)
    room.game = set_token(room.game, 0, 2, track(5))
    room.game = set_token(room.game, 0, 3, track(9))
    room.time_out(2)  # tokens 0 and 1 are in base and need a 6
    assert room.game.players[0].tokens[2] == track(7)
    assert room.game.players[0].tokens[3] == track(9)


def test_a_timed_out_roll_that_passes_the_turn_moves_nothing():
    room, _ = _started(2)
    room.game = set_token(room.game, 1, 0, track(5))  # Bob has a token that could move a 3
    room.time_out(3)  # nothing of Ann's can move on a 3
    assert room.last_roll == DieRoll(seat=0, die=3)
    assert room.game.current_seat == 1
    assert room.game.phase == Phase.AWAITING_ROLL  # Bob's turn is his to play
    assert room.game.players[1].tokens[0] == track(5)


def test_running_out_of_time_needs_a_game():
    room, _ = _room_with(2)
    with pytest.raises(GameNotStartedError):
        room.time_out(6)


# --- Colours ---------------------------------------------------------------


def test_colours_come_from_the_game():
    room, members = _room_with(3)
    assert room.colour_of(members[0]) is None  # no game yet
    room.start(members[0].session)
    assert [room.colour_of(m) for m in members] == [Colour.RED, Colour.GREEN, Colour.YELLOW]


def test_two_players_are_red_and_yellow():
    room, (ann, bob) = _started(2)
    assert (room.colour_of(ann), room.colour_of(bob)) == (Colour.RED, Colour.YELLOW)


def test_someone_who_joined_after_the_game_has_no_colour_until_the_next_start():
    room, (ann, bob) = _started(2)
    _finish_game(room)
    cat = room.join("Cat")
    assert room.colour_of(cat) is None  # the finished game has only seats 0 and 1
    assert room.colour_of(bob) == Colour.YELLOW  # players keep their colour after the game ends
    room.start(ann.session)
    assert room.colour_of(cat) == Colour.YELLOW  # 3 players: Red, Green, Yellow
    assert room.colour_of(bob) == Colour.GREEN  # Bob was Yellow in the 2-player game


# --- Registry --------------------------------------------------------------


def test_create_registers_a_room_under_its_code():
    registry = RoomRegistry()
    room = registry.create()
    assert room.code in registry
    assert registry.get(room.code) is room
    assert len(registry) == 1


def test_room_codes_are_unguessable_and_url_safe():
    registry = RoomRegistry()
    codes = [registry.create().code for _ in range(50)]
    assert len(set(codes)) == 50
    for code in codes:
        assert len(code) >= 10  # 8 random bytes -> 11 characters
        assert set(code) <= URL_SAFE


def test_an_unknown_code_is_room_not_found():
    registry = RoomRegistry()
    assert "nope" not in registry
    with pytest.raises(RoomNotFoundError):
        registry.get("nope")


def test_a_colliding_code_is_regenerated():
    codes = iter(["AAAA", "AAAA", "BBBB"])
    registry = RoomRegistry(make_code=lambda: next(codes))
    first = registry.create()
    second = registry.create()
    assert (first.code, second.code) == ("AAAA", "BBBB")
    assert registry.get("AAAA") is first  # the first room was not overwritten


def test_remove_empty_rooms_removes_only_rooms_with_nobody_connected():
    registry = RoomRegistry()
    busy, idle, never_joined = registry.create(), registry.create(), registry.create()
    busy.join("Ann")
    gone = idle.join("Bob")
    idle.disconnect(gone.session)

    removed = registry.remove_empty_rooms()

    assert sorted(removed) == sorted([idle.code, never_joined.code])
    assert busy.code in registry
    assert idle.code not in registry
    assert len(registry) == 1


# --- sessions now come from the network --------------------------------


def test_a_session_from_the_network_can_be_any_text():
    room, _ = _room_with(1)
    with pytest.raises(UnknownSessionError):  # not a TypeError or a crash
        room.disconnect("ünïcödé")
    assert room.join("Bob", session="ünïcödé").seat == 1  # unknown, so a fresh join
