from abc import ABC, abstractmethod
from models.translation import TranslationResult
from services.config.config_manager import ConfigManager


class TranslationProvider(ABC):
    @abstractmethod
    async def translate(
        self,
        text: str,
        target_language: str,
        source_language: str | None = None,
    ) -> TranslationResult:
        ...

    @abstractmethod
    async def detect_language(self, text: str) -> tuple[str, float | None]:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...
