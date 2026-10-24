from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PYLUDO_")
    turn_seconds: float = Field(30.0, gt=0)
    max_rooms: int = Field(100, gt=0)
    empty_room_seconds: float = Field(600.0, gt=0)
    sweep_seconds: float = Field(60.0, gt=0)
