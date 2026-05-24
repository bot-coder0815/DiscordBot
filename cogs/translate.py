import time
from typing import Optional, Union

import discord

from services.cache.translation_cache import TranslationCache
from services.config.config_manager import ConfigManager
from services.logging.logger import setup_logger
from services.translation.base import TranslationProvider
from services.translation.googletrans_provider import GoogletransProvider
from ui.embeds.translation_embed import build_translation_embed
from ui.views.translation_view import TranslationView

logger = setup_logger("translate_cog")


class TranslateModal(discord.ui.Modal):
    def __init__(
        self, cog: "TranslateCog", target: Optional[str] = None
    ) -> None:
        super().__init__(title="Translate Text")
        self.cog = cog
        self.target = target
        self.add_item(
            discord.ui.InputText(
                label="Text to translate",
                style=discord.InputTextStyle.long,
                placeholder="Paste or type your text here...",
                required=True,
                max_length=2000,
            )
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        text = self.children[0].value
        await interaction.response.defer(ephemeral=True)
        await self.cog._perform_translation(interaction, text, self.target)


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

    async def _perform_translation(
        self,
        responder: Union[discord.ApplicationContext, discord.Interaction],
        text: str,
        target: Optional[str] = None,
    ) -> None:
        try:
            remaining = self._check_cooldown(responder.user.id)
            if remaining is not None:
                await responder.followup.send(
                    f"Please wait {remaining}s before using this command again.",
                    ephemeral=True,
                )
                return

            if not text or not text.strip():
                await responder.followup.send(
                    "Please provide text to translate.", ephemeral=True
                )
                return

            max_len = self.config.max_text_length
            if len(text) > max_len:
                await responder.followup.send(
                    f"Text is too long ({len(text)} chars). Maximum is {max_len} chars.",
                    ephemeral=True,
                )
                return

            target_lang = (target or self.config.default_target_language).strip()

            cached = self.cache.get(text, target_lang)
            if cached:
                embed = build_translation_embed(cached)
                view = TranslationView(cached.translated_text)
                await responder.followup.send(
                    embed=embed, view=view, ephemeral=True
                )
                return

            result = await self.provider.translate(
                text=text,
                target_language=target_lang,
            )

            self.cache.set(text, target_lang, result)

            embed = build_translation_embed(result)
            view = TranslationView(result.translated_text)

            await responder.followup.send(
                embed=embed, view=view, ephemeral=True
            )

        except RuntimeError as e:
            logger.error("Translation error for %s: %s", responder.user, e)
            await responder.followup.send(
                f"Translation failed: {e}", ephemeral=True
            )
        except Exception as e:
            logger.exception("Unexpected error in /tl: %s", e)
            await responder.followup.send(
                "An unexpected error occurred. Please try again later.",
                ephemeral=True,
            )

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
        await self._perform_translation(ctx, text, target)

    @discord.slash_command(
        name="tlm",
        description="Translate longer texts with multi-line support.",
    )
    async def tlm(
        self,
        ctx: discord.ApplicationContext,
        target: Optional[str] = None,
    ) -> None:
        modal = TranslateModal(self, target)
        await ctx.send_modal(modal)

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
