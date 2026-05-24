from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TranslationResult:
    original_text: str
    translated_text: str
    detected_source_language: str
    target_language: str
    provider: str
    duration_ms: float
    source_language_confidence: Optional[float] = None
    http_version: str = "unknown"
    original_length: int = field(init=False)
    translated_length: int = field(init=False)

    def __post_init__(self) -> None:
        self.original_length = len(self.original_text)
        self.translated_length = len(self.translated_text)
