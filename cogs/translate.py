import time
from typing import Optional

import discord

from services.cache.translation_cache import TranslationCache
from services.config.config_manager import ConfigManager
from services.logging.logger import setup_logger
from services.translation.base import TranslationProvider
from services.translation.googletrans_provider import GoogletransProvider
from ui.embeds.translation_embed import build_translation_embed
from ui.views.translation_view import TranslationView

logger = setup_logger("translate_cog")


class TranslateCog(discord.Cog):
    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot
        self.config = ConfigManager()
        self.provider: TranslationProvider = self._init_provider()
        self.cache = TranslationCache(
            max_size=self.config.cache_max_size,
            enabled=self.config.cache_enabled,
        )
        self._cooldowns: dict[int, float] = {}

    def _init_provider(self) -> TranslationProvider:
        return GoogletransProvider(config=self.config)

    def _check_cooldown(self, user_id: int) -> Optional[float]:
        now = time.time()
        last = self._cooldowns.get(user_id, 0)
        remaining = self.config.cooldown_seconds - (now - last)
        if remaining > 0:
            return round(remaining, 1)
        self._cooldowns[user_id] = now
        return None

    @discord.slash_command(
        name="tl",
        description="Translate text into the configured target language.",
    )
    async def tl(
        self,
        ctx: discord.ApplicationContext,
        text: str,
        target: Optional[str] = None,
    ) -> None:
        await ctx.defer(ephemeral=True)

        try:
            remaining = self._check_cooldown(ctx.author.id)
            if remaining is not None:
                await ctx.followup.send(
                    f"Please wait {remaining}s before using this command again.",
                    ephemeral=True,
                )
                return

            if not text or not text.strip():
                await ctx.followup.send(
                    "Please provide text to translate.", ephemeral=True
                )
                return

            max_len = self.config.max_text_length
            if len(text) > max_len:
                await ctx.followup.send(
                    f"Text is too long ({len(text)} chars). Maximum is {max_len} chars.",
                    ephemeral=True,
                )
                return

            target_lang = (target or self.config.default_target_language).strip()

            cached = self.cache.get(text, target_lang)
            if cached:
                embed = build_translation_embed(cached)
                view = TranslationView(cached.translated_text)
                await ctx.followup.send(embed=embed, view=view, ephemeral=True)
                return

            result = await self.provider.translate(
                text=text,
                target_language=target_lang,
            )

            self.cache.set(text, target_lang, result)

            embed = build_translation_embed(result)
            view = TranslationView(result.translated_text)

            await ctx.followup.send(embed=embed, view=view, ephemeral=True)

        except RuntimeError as e:
            logger.error("Translation error for %s: %s", ctx.author, e)
            await ctx.followup.send(
                f"Translation failed: {e}", ephemeral=True
            )
        except Exception as e:
            logger.exception("Unexpected error in /tl: %s", e)
            await ctx.followup.send(
                "An unexpected error occurred. Please try again later.",
                ephemeral=True,
            )

    @tl.error
    async def tl_error(
        self,
        ctx: discord.ApplicationContext,
        error: discord.DiscordException,
    ) -> None:
        logger.error("Command error for %s: %s", ctx.author, error)
        try:
            await ctx.followup.send(
                f"An error occurred: {error}", ephemeral=True
            )
        except Exception:
            pass

    @discord.Cog.listener()
    async def on_ready(self) -> None:
        logger.info("TranslateCog loaded")


def setup(bot: discord.Bot) -> None:
    bot.add_cog(TranslateCog(bot))
