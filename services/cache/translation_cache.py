from collections import OrderedDict
from typing import Optional

from models.translation import TranslationResult


class TranslationCache:
    def __init__(self, max_size: int = 500, enabled: bool = True) -> None:
        self._max_size = max_size
        self._enabled = enabled
        self._cache: OrderedDict[str, TranslationResult] = OrderedDict()

    def _make_key(
        self, text: str, target_language: str, source_language: Optional[str]
    ) -> str:
        return f"{source_language or 'auto'}:{target_language}:{hash(text)}"

    def get(
        self, text: str, target_language: str, source_language: Optional[str] = None
    ) -> Optional[TranslationResult]:
        if not self._enabled:
            return None
        key = self._make_key(text, target_language, source_language)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(
        self,
        text: str,
        target_language: str,
        result: TranslationResult,
        source_language: Optional[str] = None,
    ) -> None:
        if not self._enabled:
            return
        key = self._make_key(text, target_language, source_language)
        self._cache[key] = result
        self._cache.move_to_end(key)
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:
            self._cache.clear()
