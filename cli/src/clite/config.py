"""Конфигурация CLI: загрузка из ~/.config/clite/config.yaml + env."""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_API_URL = "https://apitracker.ru"
CONFIG_PATH = Path.home() / ".config" / "clite" / "config.yaml"


@dataclass(frozen=True)
class Config:
    api_url: str = DEFAULT_API_URL
    token: str | None = None

    @property
    def base_url(self) -> str:
        return self.api_url.rstrip("/")


def load_config() -> Config:
    data: dict[str, object] = {}
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if isinstance(loaded, dict):
            data = loaded
    env_url = os.environ.get("APIT_API_URL")
    env_token = os.environ.get("APIT_TOKEN")

    api_url = env_url or str(data.get("api_url") or DEFAULT_API_URL)
    token_val = env_token if env_token is not None else data.get("token")
    token = str(token_val) if token_val else None
    return Config(api_url=api_url, token=token)
