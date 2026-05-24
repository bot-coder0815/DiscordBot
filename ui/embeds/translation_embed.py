import discord

from models.translation import TranslationResult
from utils.helpers import get_language_name, format_duration, truncate_text


FIELD_MAX = 1024


def build_translation_embed(result: TranslationResult) -> discord.Embed:
    source_name = get_language_name(result.detected_source_language)
    target_name = get_language_name(result.target_language)

    embed = discord.Embed(
        title="Translation",
        colour=0x00b0f4,
    )

    original = truncate_text(result.original_text, FIELD_MAX)
    translated = truncate_text(result.translated_text, FIELD_MAX)

    embed.add_field(name="Original Text", value=original, inline=False)
    embed.add_field(name="Translated Text", value=translated, inline=False)

    info_parts = [
        f"Detected: **{source_name}** `{result.detected_source_language}`",
        f"Target: **{target_name}** `{result.target_language}`",
        f"Duration: `{format_duration(result.duration_ms)}`",
        f"Provider: **{result.provider}**",
        f"HTTP: `{result.http_version}`",
    ]

    if result.source_language_confidence is not None:
        conf = round(result.source_language_confidence * 100, 1)
        info_parts.insert(2, f"Confidence: `{conf}%`")

    embed.add_field(name="Details", value="\n".join(info_parts), inline=False)

    return embed
