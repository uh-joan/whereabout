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
    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    @classmethod
    def load(cls) -> "UserConfig":
        if not CONFIG_PATH.exists():
            return cls()
        with open(CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
        return cls(**data)

    def save(self) -> None:
        import os
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = tomli_w.dumps(self.model_dump()).encode()
        fd = os.open(str(CONFIG_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)

    def is_first_run(self) -> bool:
        return not CONFIG_PATH.exists() or not self.home_neighbourhood
