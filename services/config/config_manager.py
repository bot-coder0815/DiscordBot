import json
import os
from typing import Any


DEFAULT_CONFIG = {
    "default_target_language": "en",
    "cache_enabled": True,
    "cache_max_size": 500,
    "cooldown_seconds": 5,
    "max_text_length": 15000,
    "request_timeout": 15,
    "max_retries": 3,
    "retry_delay": 1.0,
    "service_urls": ["translate.googleapis.com"],
}


class ConfigManager:
    def __init__(self, config_path: str = "config/config.json") -> None:
        self.config_path = config_path
        self._data: dict[str, Any] = dict(DEFAULT_CONFIG)
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self._data.update(loaded)
            except (json.JSONDecodeError, OSError):
                pass

    def reload(self) -> None:
        self._data = dict(DEFAULT_CONFIG)
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    @property
    def default_target_language(self) -> str:
        return str(self.get("default_target_language", "EN"))

    @property
    def cache_enabled(self) -> bool:
        return bool(self.get("cache_enabled", True))

    @property
    def cache_max_size(self) -> int:
        return int(self.get("cache_max_size", 500))

    @property
    def cooldown_seconds(self) -> int:
        return int(self.get("cooldown_seconds", 5))

    @property
    def max_text_length(self) -> int:
        return int(self.get("max_text_length", 5000))

    @property
    def request_timeout(self) -> int:
        return int(self.get("request_timeout", 15))

    @property
    def max_retries(self) -> int:
        return int(self.get("max_retries", 3))

    @property
    def retry_delay(self) -> float:
        return float(self.get("retry_delay", 1.0))
