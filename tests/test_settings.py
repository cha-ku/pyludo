import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from pyludo.server import create_app
from pyludo.settings import Settings

FIELDS = ["turn_seconds", "max_rooms", "empty_room_seconds", "sweep_seconds"]


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Start every test with no PYLUDO_ variables, whatever the shell running pytest has set."""
    for field in FIELDS:
        monkeypatch.delenv(f"PYLUDO_{field.upper()}", raising=False)


def test_the_defaults():
    settings = Settings()
    assert settings.turn_seconds == 30.0
    assert settings.max_rooms == 100
    assert settings.empty_room_seconds == 600.0  # ten minutes
    assert settings.sweep_seconds == 60.0


def test_each_setting_comes_from_a_pyludo_environment_variable(monkeypatch):
    monkeypatch.setenv("PYLUDO_TURN_SECONDS", "20")
    monkeypatch.setenv("PYLUDO_MAX_ROOMS", "5")
    monkeypatch.setenv("PYLUDO_EMPTY_ROOM_SECONDS", "120.5")
    monkeypatch.setenv("PYLUDO_SWEEP_SECONDS", "10")
    settings = Settings()
    assert settings.turn_seconds == 20.0  # environment variables are text: Pydantic converts them
    assert settings.max_rooms == 5
    assert settings.empty_room_seconds == 120.5
    assert settings.sweep_seconds == 10.0


def test_a_variable_without_the_prefix_is_ignored(monkeypatch):
    monkeypatch.setenv("MAX_ROOMS", "5")  # could belong to any program
    assert Settings().max_rooms == 100


def test_values_passed_in_win_over_the_environment(monkeypatch):
    monkeypatch.setenv("PYLUDO_TURN_SECONDS", "20")
    assert Settings(turn_seconds=0.3).turn_seconds == 0.3  # how the tests pick short turns


@pytest.mark.parametrize("field", FIELDS)
def test_text_that_isnt_a_number_is_refused(monkeypatch, field):
    monkeypatch.setenv(f"PYLUDO_{field.upper()}", "soon")
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", ["0", "-1"])
def test_zero_or_less_is_refused(monkeypatch, field, value):
    monkeypatch.setenv(f"PYLUDO_{field.upper()}", value)
    with pytest.raises(ValidationError):
        Settings()


def test_max_rooms_must_be_a_whole_number(monkeypatch):
    monkeypatch.setenv("PYLUDO_MAX_ROOMS", "2.5")
    with pytest.raises(ValidationError):
        Settings()


def test_the_app_reads_its_settings_from_the_environment(monkeypatch):
    monkeypatch.setenv("PYLUDO_MAX_ROOMS", "1")
    client = TestClient(create_app())
    assert client.post("/rooms", follow_redirects=False).status_code == 303
    assert client.post("/rooms", follow_redirects=False).status_code == 503  # one too many
