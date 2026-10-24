"""The turn timer on its own, without a server.

Each test runs a small async scenario with asyncio.run(). Times are short multiples of TICK: long
enough to tell "not yet" from "done" reliably, short enough to keep the suite fast.
"""

import asyncio

import pytest

from pyludo.timers import TurnTimer

pytestmark = pytest.mark.timeout(5)

TICK = 0.05  # seconds


def test_the_timer_calls_back_once_when_its_time_is_up():
    async def scenario():
        calls = []

        async def on_expiry():
            calls.append("expired")

        timer = TurnTimer(2 * TICK, on_expiry)
        timer.start()
        await asyncio.sleep(TICK)
        assert calls == []  # not yet
        await asyncio.sleep(3 * TICK)
        assert calls == ["expired"]  # once, and only once

    asyncio.run(scenario())


def test_starting_again_restarts_the_countdown():
    async def scenario():
        calls = []

        async def on_expiry():
            calls.append("expired")

        timer = TurnTimer(2 * TICK, on_expiry)
        timer.start()
        await asyncio.sleep(1.5 * TICK)
        timer.start()  # someone acted: the next turn gets the full time
        await asyncio.sleep(TICK)
        assert calls == []  # the first countdown would have ended by now
        await asyncio.sleep(2 * TICK)
        assert calls == ["expired"]

    asyncio.run(scenario())


def test_a_stopped_timer_never_calls_back():
    async def scenario():
        calls = []

        async def on_expiry():
            calls.append("expired")

        timer = TurnTimer(TICK, on_expiry)
        timer.start()
        timer.stop()
        await asyncio.sleep(3 * TICK)
        assert calls == []

    asyncio.run(scenario())


def test_seconds_left_counts_down_while_running_and_is_none_otherwise():
    async def scenario():
        async def on_expiry():
            pass

        timer = TurnTimer(4 * TICK, on_expiry)
        assert timer.seconds_left is None  # never started
        timer.start()
        assert 3 * TICK < timer.seconds_left <= 4 * TICK
        await asyncio.sleep(2 * TICK)
        assert timer.seconds_left < 3 * TICK
        timer.stop()
        assert timer.seconds_left is None
        timer.start()
        await asyncio.sleep(5 * TICK)
        assert timer.seconds_left is None  # it expired

    asyncio.run(scenario())


def test_the_callback_can_start_the_next_countdown():
    # What the server does: when time runs out it plays the turn, starts the next player's
    # countdown, and only then awaits sending the snapshot.
    async def scenario():
        finished = []
        timer = None

        async def on_expiry():
            timer.start()
            await asyncio.sleep(0)  # stands in for the broadcast
            finished.append("expired")

        timer = TurnTimer(2 * TICK, on_expiry)
        timer.start()
        await asyncio.sleep(3 * TICK)
        assert finished == ["expired"]  # starting the next countdown didn't cancel this callback
        assert timer.seconds_left is not None  # and the next countdown is running
        timer.stop()

    asyncio.run(scenario())
