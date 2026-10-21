import secrets
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .board_layout import CENTRE, YARD_ORIGIN, base_cell, home_column_cell, track_cell
from .engine.models import Colour
from .engine.path import HOME_COLUMN_LENGTH, RING_SIZE, SAFE_SQUARES, TOKENS_PER_PLAYER
from .rooms import RoomRegistry


def roll_die() -> int:
    return secrets.randbelow(6) + 1


def create_app(
    registry: RoomRegistry | None = None, roll_die: Callable[[], int] = roll_die
) -> FastAPI:
    registry = registry if registry is None else RoomRegistry()
    app = FastAPI()
    BASE_DIR = Path(__file__).parent
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")

    @app.get("/healthz")
    async def health_check():
        return {"status": "ok"}

    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse(
            request,
            "board.html",
            {
                "track": [track_cell(i) for i in range(RING_SIZE)],
                "safe_squares": SAFE_SQUARES,
                "home_columns": {
                    c: [home_column_cell(c, i) for i in range(HOME_COLUMN_LENGTH)] for c in Colour
                },
                "base_slots": {
                    c: [base_cell(c, i) for i in range(TOKENS_PER_PLAYER)] for c in Colour
                },
                "yards": YARD_ORIGIN,
                "centre": CENTRE,
            },
        )

    return app


app = create_app()
