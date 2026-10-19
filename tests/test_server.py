from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from pyludo.board_layout import CENTRE, YARD_ORIGIN, base_cell, home_column_cell, track_cell
from pyludo.engine.models import Colour
from pyludo.engine.path import SAFE_SQUARES
from pyludo.server import app


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
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def page(client):
    return client.get("/")


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


def test_index_is_an_html_page(page):
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert page.text.lstrip().lower().startswith("<!doctype html>")


def test_the_page_links_a_stylesheet_that_is_served(client, page):
    links = [a for tag, a in _elements(page.text) if tag == "link" and a.get("rel") == "stylesheet"]
    assert links, "no <link rel='stylesheet'> in the page"
    css = client.get(links[0]["href"])
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")


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
