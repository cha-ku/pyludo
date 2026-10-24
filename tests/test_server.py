from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from pyludo.board_layout import CENTRE, YARD_ORIGIN, base_cell, home_column_cell, track_cell
from pyludo.engine.models import Colour
from pyludo.engine.path import SAFE_SQUARES
from pyludo.rooms import MAX_NICKNAME_LEN, RoomRegistry
from pyludo.server import create_app


class _Elements(HTMLParser):
    """Collects every start tag as (tag, attrs) in document order.

    HTMLParser lowercases tag and attribute names, so `viewBox` arrives as `viewbox`.
    """

    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag, attrs):
        self.found.append((tag, {k: v or "" for k, v in attrs}))


def _elements(html: str) -> list[tuple[str, dict[str, str]]]:
    parser = _Elements()
    parser.feed(html)
    return parser.found


def _classes(attrs: dict[str, str]) -> set[str]:
    return set(attrs.get("class", "").split())


def _cell_of(attrs: dict[str, str]) -> tuple[int, int]:
    """(row, col) of a rect. SVG x is the column and y is the row."""
    return int(float(attrs["y"])), int(float(attrs["x"]))


@pytest.fixture(scope="module")
def registry():
    return RoomRegistry()


@pytest.fixture(scope="module")
def client(registry):
    return TestClient(create_app(registry=registry))


@pytest.fixture(scope="module")
def room(registry):
    return registry.create()


@pytest.fixture(scope="module")
def landing(client):
    return client.get("/")


@pytest.fixture(scope="module")
def page(client, room):
    """The room page, which is where the board lives from M5 on."""
    return client.get(f"/r/{room.code}")


@pytest.fixture(scope="module")
def rects(page):
    return [attrs for tag, attrs in _elements(page.text) if tag == "rect"]


def _with_class(rects, name):
    return [r for r in rects if name in _classes(r)]


# --- Plain routes ----------------------------------------------------------


def test_healthz_reports_ok_as_json(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {"status": "ok"}


def test_unknown_paths_are_404(client):
    assert client.get("/no-such-page").status_code == 404


def _assert_html_page(response) -> None:
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text.lstrip().lower().startswith("<!doctype html>")


def test_the_landing_page_and_the_room_page_are_html(landing, page):
    _assert_html_page(landing)
    _assert_html_page(page)


@pytest.mark.parametrize("which", ["landing", "page"])
def test_both_pages_link_a_stylesheet_that_is_served(client, request, which):
    html = request.getfixturevalue(which).text
    links = [a for tag, a in _elements(html) if tag == "link" and a.get("rel") == "stylesheet"]
    assert links, "no <link rel='stylesheet'> in the page"
    css = client.get(links[0]["href"])
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")


# --- Creating a room -------------------------------------------------------


def test_the_landing_page_has_a_form_that_posts_to_rooms(landing):
    elements = _elements(landing.text)
    forms = [a for tag, a in elements if tag == "form"]
    assert len(forms) == 1
    assert forms[0].get("method", "").lower() == "post"
    assert forms[0].get("action") == "/rooms"
    assert any(tag == "button" for tag, _ in elements), "no button to submit the form"


def test_the_landing_page_has_no_board(landing):
    assert not any(tag == "svg" for tag, _ in _elements(landing.text))


def test_creating_a_room_redirects_to_its_page():
    registry = RoomRegistry()
    client = TestClient(create_app(registry=registry))
    r = client.post("/rooms", follow_redirects=False)
    assert r.status_code == 303  # See Other: "now GET this other page"
    location = r.headers["location"]
    assert location.startswith("/r/")
    code = location.removeprefix("/r/")
    assert code in registry
    assert len(registry) == 1
    _assert_html_page(client.get(location))


def test_every_post_creates_a_new_room():
    registry = RoomRegistry()
    client = TestClient(create_app(registry=registry))
    first = client.post("/rooms", follow_redirects=False).headers["location"]
    second = client.post("/rooms", follow_redirects=False).headers["location"]
    assert first != second
    assert len(registry) == 2


def test_a_room_cannot_be_created_with_get(client, registry):
    rooms_before = len(registry)
    assert client.get("/rooms").status_code == 405  # Method Not Allowed: GET must not change things
    assert len(registry) == rooms_before


def test_a_created_room_can_be_joined_over_the_websocket():
    client = TestClient(create_app(registry=RoomRegistry()))
    code = client.post("/rooms", follow_redirects=False).headers["location"].removeprefix("/r/")
    with client.websocket_connect(f"/ws/{code}") as ws:
        ws.send_json({"type": "hello", "nickname": "Ann"})
        assert ws.receive_json()["type"] == "welcome"


# --- The room page ---------------------------------------------------------


def test_the_room_page_shows_the_room_code(page, room):
    assert room.code in page.text


def test_an_unknown_room_is_404(client):
    assert client.get("/r/no-such-room").status_code == 404


# --- What app.js needs from the room page ----------------------------------
# app.js itself is checked by hand (the checklist in PRIMER.md). These tests pin down what it
# expects to find in the page, so renaming an id in the template fails here instead of quietly
# breaking the game in the browser.


def _the_one_with_id(html: str, id_: str) -> tuple[str, dict[str, str]]:
    found = [(tag, attrs) for tag, attrs in _elements(html) if attrs.get("id") == id_]
    assert len(found) == 1, f"expected one element with id={id_!r}, found {len(found)}"
    return found[0]


def test_the_room_page_loads_app_js_as_a_module_that_is_served(client, page):
    scripts = [attrs for tag, attrs in _elements(page.text) if tag == "script"]
    assert len(scripts) == 1
    assert scripts[0].get("type") == "module"
    assert scripts[0].get("src", "").endswith("/app.js")
    js = client.get(scripts[0]["src"])
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]


def test_the_landing_page_needs_no_script(landing):
    assert not any(tag == "script" for tag, _ in _elements(landing.text))


def test_the_room_page_tells_the_script_its_room_code(page, room):
    holders = [attrs for _, attrs in _elements(page.text) if "data-code" in attrs]
    assert [attrs["data-code"] for attrs in holders] == [room.code]


def test_the_room_page_has_a_nickname_form(page):
    assert _the_one_with_id(page.text, "join")[0] == "form"
    elements = _elements(page.text)
    inputs = [a for tag, a in elements if tag == "input" and a.get("name") == "nickname"]
    assert len(inputs) == 1
    assert "required" in inputs[0]  # the browser refuses an empty nickname before the server has to
    assert inputs[0].get("maxlength") == str(MAX_NICKNAME_LEN)


@pytest.mark.parametrize("id_", ["members", "status", "timer", "error"])
def test_the_room_page_has_the_places_app_js_writes_into(page, id_):
    _the_one_with_id(page.text, id_)


@pytest.mark.parametrize("id_", ["start", "roll"])
def test_the_game_buttons_are_hidden_until_app_js_shows_them(page, id_):
    tag, attrs = _the_one_with_id(page.text, id_)
    assert tag == "button"
    assert "hidden" in attrs


def test_the_board_has_an_empty_group_for_the_tokens_drawn_last(page):
    svg = page.text[page.text.index("<svg") : page.text.index("</svg>")]
    elements = _elements(svg)
    ids = [attrs.get("id") for _, attrs in elements]
    assert ids.count("tokens") == 1, "no element with id='tokens' inside the board's <svg>"
    tokens = ids.index("tokens")
    assert elements[tokens][0] == "g"
    assert tokens == len(elements) - 1  # nothing after it: tokens paint on top of every square


# --- The SVG board ---------------------------------------------------------


def test_the_board_is_one_15x15_svg(page):
    svgs = [a for tag, a in _elements(page.text) if tag == "svg"]
    assert len(svgs) == 1
    assert svgs[0].get("viewbox") == "0 0 15 15"


def test_track_squares(rects):
    track = _with_class(rects, "track")
    assert len(track) == 52
    assert sorted(int(r["data-index"]) for r in track) == list(range(52))
    for r in track:
        assert _cell_of(r) == track_cell(int(r["data-index"])), r
        assert (r["width"], r["height"]) == ("1", "1")


def test_exactly_the_safe_squares_are_marked_safe(rects):
    safe = _with_class(rects, "safe")
    assert all("track" in _classes(r) for r in safe)
    assert {int(r["data-index"]) for r in safe} == SAFE_SQUARES
    assert len(safe) == 8


def test_home_column_squares(rects):
    homes = _with_class(rects, "home")
    assert len(homes) == 20
    for r in homes:
        colour, index = Colour(r["data-colour"]), int(r["data-index"])
        assert _cell_of(r) == home_column_cell(colour, index), r
    assert {(r["data-colour"], r["data-index"]) for r in homes} == {
        (c.value, str(i)) for c in Colour for i in range(5)
    }


def test_base_slots(rects):
    bases = _with_class(rects, "base")
    assert len(bases) == 16
    for r in bases:
        colour, index = Colour(r["data-colour"]), int(r["data-index"])
        assert _cell_of(r) == base_cell(colour, index), r
    assert {(r["data-colour"], r["data-index"]) for r in bases} == {
        (c.value, str(i)) for c in Colour for i in range(4)
    }


def test_centre_square(rects):
    centre = _with_class(rects, "centre")
    assert len(centre) == 1
    assert _cell_of(centre[0]) == CENTRE


def test_yards_are_6x6_and_drawn_before_the_base_slots(rects):
    yards = _with_class(rects, "yard")
    assert {Colour(r["data-colour"]): _cell_of(r) for r in yards} == YARD_ORIGIN
    assert all((r["width"], r["height"]) == ("6", "6") for r in yards)
    # SVG paints in document order, so a yard drawn after a base slot would hide it.
    last_yard = max(rects.index(r) for r in yards)
    first_base = min(rects.index(r) for r in _with_class(rects, "base"))
    assert last_yard < first_base
