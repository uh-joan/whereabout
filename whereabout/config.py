from __future__ import annotations
import tomllib
import tomli_w
from pathlib import Path
from pydantic import BaseModel


CONFIG_PATH = Path.home() / ".config" / "whereabout" / "config.toml"


class UserConfig(BaseModel):
    home_neighbourhood: str = ""
    default_horizon_days: int = 14
    default_result_limit: int = 10
    preferred_genres: list[str] = []

    @classmethod
    def load(cls) -> "UserConfig":
        if not CONFIG_PATH.exists():
            return cls()
        with open(CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
        return cls(**data)

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_bytes(tomli_w.dumps(self.model_dump()).encode())

    def is_first_run(self) -> bool:
        return not CONFIG_PATH.exists() or not self.home_neighbourhood
