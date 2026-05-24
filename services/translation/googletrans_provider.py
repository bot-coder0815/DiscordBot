import asyncio
import time
from typing import Optional

from googletrans import Translator

from models.translation import TranslationResult
from services.config.config_manager import ConfigManager
from services.logging.logger import setup_logger
from services.translation.base import TranslationProvider

logger = setup_logger("googletrans")


class GoogletransProvider(TranslationProvider):
    def __init__(self, config: ConfigManager) -> None:
        self._config = config
        self._http_version: str = "HTTP/2"

    @property
    def provider_name(self) -> str:
        return "googletrans"

    @property
    def http_version(self) -> str:
        return self._http_version

    async def _translate_with_retry(
        self,
        translator: Translator,
        text: str,
        dest: str,
        src: str = "auto",
    ) -> tuple[dict, float]:
        start_time = time.perf_counter()
        last_error: Optional[Exception] = None
        max_retries = self._config.max_retries

        for attempt in range(max_retries):
            try:
                result = await translator.translate(text, dest=dest, src=src)
                if result is None:
                    raise RuntimeError("googletrans returned None")
                duration = (time.perf_counter() - start_time) * 1000
                return result, duration
            except (Exception, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(self._config.retry_delay)
                    continue

        raise RuntimeError(
            f"Translation failed after {max_retries} retries: {last_error}"
        )

    async def detect_language(self, text: str) -> tuple[str, Optional[float]]:
        max_retries = self._config.max_retries
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                async with Translator(
                    service_urls=self._config.get("service_urls", []),
                ) as translator:
                    detected = await translator.detect(text)
                    return detected.lang, detected.confidence
            except (Exception, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(self._config.retry_delay)
                    continue

        logger.error("Language detection failed: %s", last_error)
        return "und", None

    async def translate(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None,
    ) -> TranslationResult:
        
        service_urls = self._config.get("service_urls", [])
        if not service_urls:
            service_urls = ["translate.googleapis.com"]

        src = source_language if source_language else "auto"

        async with Translator(service_urls=service_urls) as translator:
            result, duration = await self._translate_with_retry(
                translator, text, dest=target_language, src=src,
            )

            translated_text = getattr(result, "text", None) or str(result)
            detected_lang = getattr(result, "src", src if src != "auto" else "und")
            confidence = getattr(result, "confidence", None)

        return TranslationResult(
            original_text=text,
            translated_text=translated_text,
            detected_source_language=detected_lang,
            target_language=target_language,
            provider=self.provider_name,
            duration_ms=round(duration, 2),
            source_language_confidence=confidence,
            http_version=self._http_version,
        )

    async def close(self) -> None:
        pass
