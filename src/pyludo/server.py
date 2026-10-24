import asyncio
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .board_layout import CENTRE, YARD_ORIGIN, base_cell, home_column_cell, track_cell
from .engine.errors import LudoError
from .engine.models import Colour, Phase
from .engine.path import HOME_COLUMN_LENGTH, RING_SIZE, SAFE_SQUARES, TOKENS_PER_PLAYER
from .protocol import (
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
from .rooms import Room, RoomRegistry
from .timers import TurnTimer


# Lock is needed here because changes to room should be atomic.
# so each room needs to hold its lock when making changes to the
# state. Since we hold the lock when changing the state, we also
# need to hold it when sending communicating the change, i.e.
# getting a snapshot from the room.
class PerRoomResources(NamedTuple):
    lock: asyncio.Lock
    sockets: list[WebSocket]
    timer: TurnTimer


def roll_die() -> int:
    return secrets.randbelow(6) + 1


def create_app(
    registry: RoomRegistry | None = None,
    roll_die: Callable[[], int] = roll_die,
    turn_seconds: float = 30.0,
) -> FastAPI:
    registry = registry if registry is not None else RoomRegistry()
    app = FastAPI()
    BASE_DIR = Path(__file__).parent
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    resources_per_room: dict[str, PerRoomResources] = {}
    board = {
        "track": [track_cell(i) for i in range(RING_SIZE)],
        "safe_squares": SAFE_SQUARES,
        "home_columns": {
            c: [home_column_cell(c, i) for i in range(HOME_COLUMN_LENGTH)] for c in Colour
        },
        "base_slots": {c: [base_cell(c, i) for i in range(TOKENS_PER_PLAYER)] for c in Colour},
        "yards": YARD_ORIGIN,
        "centre": CENTRE,
    }

    @app.get("/healthz")
    async def health_check():
        return {"status": "ok"}

    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse(request, "landing.html")

    @app.post("/rooms")
    def create_room():
        room = registry.create()
        return RedirectResponse(f"/r/{room.code}", status_code=303)

    @app.get("/r/{code}")
    def room(request: Request, code: str):
        if code not in registry:
            raise HTTPException(status_code=404, detail="Room not found")
        return templates.TemplateResponse(request, "room.html", {"code": code, **board})

    async def _send_error(websocket: WebSocket, exception: LudoError):
        err = Error.from_exception(exception)
        try:
            await websocket.send_text(err.model_dump_json())
        except Exception:
            pass

    async def _broadcast_snapshot(room: Room):
        timer = resources_per_room[room.code].timer
        snapshot = Snapshot.from_room(room, timer.seconds_left).model_dump_json()
        for ws in resources_per_room[room.code].sockets:
            try:
                await ws.send_text(snapshot)
            except Exception:
                pass

    def _resources_for(room: Room) -> PerRoomResources:
        if room.code not in resources_per_room:
            lock = asyncio.Lock()

            async def on_expiry():
                async with lock:
                    room.time_out(roll_die())
                    await _after_change(room)

            timer = TurnTimer(turn_seconds, on_expiry)
            resources_per_room[room.code] = PerRoomResources(lock, [], timer)
        return resources_per_room[room.code]

    async def _after_change(room: Room):
        timer = resources_per_room[room.code].timer
        if room.game is not None and room.game.phase != Phase.GAME_OVER:
            timer.start()
        else:
            timer.stop()
        await _broadcast_snapshot(room)

    # Normal message flow
    # client   |                | server
    # -------- |                | ------
    # A Hello  | -------------->|
    #          |<-------------- | Welcome A
    #          |<-------------- | Snapshot (broadcast - [A])
    # B Hello  | -------------->|
    #          |<-------------- | Welcome B
    #          |<-------------- | Snapshot (broadcast - [A, B])
    # A Start  | -------------->|
    #          |<-------------- | Snapshot (broadcast - [A, B])
    # A Roll   | -------------->|
    #          |<-------------- | Snapshot (broadcast - [A, B])
    #    .     | -------------->|    .
    #    .     |<-------------- |    .

    # A and B both websockets remain connected during this time, until the clients
    # themselves are disconnected. Errors are communicated to the client but the clients
    # stay connected

    @app.websocket("/ws/{code}")
    async def accept(websocket: WebSocket, code: str):
        await websocket.accept()

        try:
            room = registry.get(code)
            hello = parse_client_message(await websocket.receive_text())
            if not isinstance(hello, Hello):
                raise InvalidMessageError("Say Hello first")

            resources = _resources_for(room)
            lock = resources.lock
            async with lock:
                new_member = room.join(hello.nickname, hello.session if hello.session else None)
                session = new_member.session
                resources.sockets.append(websocket)
                await websocket.send_text(
                    Welcome(session=session, seat=new_member.seat).model_dump_json()
                )
                await _broadcast_snapshot(room)
            try:
                while True:
                    try:
                        message = parse_client_message(await websocket.receive_text())
                        async with lock:
                            match message:
                                case Start():
                                    room.start(session)
                                case Roll():
                                    room.roll(session, roll_die())
                                case Move():
                                    room.move(session, message.token)
                                case Hello():
                                    raise InvalidMessageError("sent Hello again")
                            await _after_change(room)

                    except LudoError as err:
                        await _send_error(websocket, err)

            except WebSocketDisconnect:
                async with lock:
                    room.disconnect(session)
                    resources.sockets.remove(websocket)
                    await _broadcast_snapshot(room)

        except LudoError as err:
            await _send_error(websocket, err)
            await websocket.close()

    return app


app = create_app()
