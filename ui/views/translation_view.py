import discord


class TranslationView(discord.ui.View):
    def __init__(self, translated_text: str) -> None:
        super().__init__(timeout=300)
        self._translated_text = translated_text

    @discord.ui.button(
        label="Copy Translation",
        style=discord.ButtonStyle.primary,
        emoji="📋",
        custom_id="translate:copy",
    )
    async def copy_translation(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        await interaction.response.send_message(
            self._translated_text,
            ephemeral=True,
        )
