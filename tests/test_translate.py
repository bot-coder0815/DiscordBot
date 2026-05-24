import pytest

from models.translation import TranslationResult
from services.cache.translation_cache import TranslationCache


class TestTranslationResult:
    def test_initialization(self) -> None:
        result = TranslationResult(
            original_text="Hello",
            translated_text="Hallo",
            detected_source_language="en",
            target_language="de",
            provider="googletrans",
            duration_ms=123.45,
        )
        assert result.original_length == 5
        assert result.translated_length == 5
        assert result.original_text == "Hello"
        assert result.translated_text == "Hallo"
        assert result.http_version == "unknown"

    def test_with_confidence(self) -> None:
        result = TranslationResult(
            original_text="Hola",
            translated_text="Hello",
            detected_source_language="es",
            target_language="en",
            provider="googletrans",
            duration_ms=50.0,
            source_language_confidence=0.95,
            http_version="HTTP/2",
        )
        assert result.source_language_confidence == 0.95
        assert result.http_version == "HTTP/2"


class TestTranslationCache:
    def test_cache_set_and_get(self) -> None:
        cache = TranslationCache(max_size=100, enabled=True)
        result = TranslationResult(
            original_text="Hello",
            translated_text="Hallo",
            detected_source_language="en",
            target_language="de",
            provider="googletrans",
            duration_ms=100.0,
        )
        cache.set("Hello", "de", result)
        cached = cache.get("Hello", "de")
        assert cached is not None
        assert cached.translated_text == "Hallo"

    def test_cache_miss(self) -> None:
        cache = TranslationCache(max_size=100, enabled=True)
        result = cache.get("Hello", "fr")
        assert result is None

    def test_cache_disabled(self) -> None:
        cache = TranslationCache(max_size=100, enabled=False)
        result = TranslationResult(
            original_text="Hello",
            translated_text="Bonjour",
            detected_source_language="en",
            target_language="fr",
            provider="googletrans",
            duration_ms=100.0,
        )
        cache.set("Hello", "fr", result)
        cached = cache.get("Hello", "fr")
        assert cached is None

    def test_cache_max_size(self) -> None:
        cache = TranslationCache(max_size=2, enabled=True)
        for i in range(5):
            result = TranslationResult(
                original_text=str(i),
                translated_text=str(i),
                detected_source_language="en",
                target_language="de",
                provider="googletrans",
                duration_ms=10.0,
            )
            cache.set(str(i), "de", result)
        assert cache.size <= 2

    def test_cache_clear(self) -> None:
        cache = TranslationCache(max_size=100, enabled=True)
        result = TranslationResult(
            original_text="Hello",
            translated_text="Hallo",
            detected_source_language="en",
            target_language="de",
            provider="googletrans",
            duration_ms=100.0,
        )
        cache.set("Hello", "de", result)
        cache.clear()
        assert cache.size == 0
