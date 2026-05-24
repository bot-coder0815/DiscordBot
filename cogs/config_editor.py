import json
import os

import discord

from services.logging.logger import setup_logger
from services.ticket.config import TicketConfig

logger = setup_logger("config_editor")

CONFIG_FILE = "ticket_config.json"


class SectionEditModal(discord.ui.Modal):
    def __init__(self, section_key: str, section_data: dict) -> None:
        pretty = json.dumps(section_data, indent=2, ensure_ascii=False)
        super().__init__(title=f"Config: {section_key}")
        self.section_key = section_key
        self.add_item(
            discord.ui.InputText(
                label=f"Edit {section_key}",
                style=discord.InputTextStyle.long,
                value=pretty,
                required=True,
            )
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        raw = self.children[0].value
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            await interaction.response.send_message(
                f"Invalid JSON: {e}", ephemeral=True
            )
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                full = json.load(f)
        except Exception:
            await interaction.response.send_message(
                "Could not read config file.", ephemeral=True
            )
            return

        full[self.section_key] = parsed

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(full, f, indent=2, ensure_ascii=False)
        except Exception as e:
            await interaction.response.send_message(
                f"Failed to save: {e}", ephemeral=True
            )
            return

        TicketConfig.reload()

        embed = discord.Embed(
            title="Config Updated",
            description=f"**{self.section_key}** saved successfully.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ConfigSectionSelect(discord.ui.Select):
    def __init__(self, config_data: dict) -> None:
        self._data = config_data
        options = [
            discord.SelectOption(
                label=key.replace("_", " ").title(),
                value=key,
                description=f"Edit {key} settings",
            )
            for key in config_data
        ]
        super().__init__(
            placeholder="Select a config section to edit...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        section = self.values[0]
        section_data = self._data.get(section, {})
        pretty = json.dumps(section_data, indent=2, ensure_ascii=False)
        if len(pretty) > 1000:
            pretty = pretty[:1000] + "\n..."

        embed = discord.Embed(
            title=f"Config: {section.replace('_', ' ').title()}",
            description=f"```json\n{pretty}\n```",
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Click Edit to modify | Back to return")

        view = SectionDetailView(section, section_data, self._data)
        await interaction.response.edit_message(embed=embed, view=view)


class SectionDetailView(discord.ui.View):
    def __init__(self, section_key: str, section_data: dict, config_data: dict) -> None:
        super().__init__(timeout=300)
        self.section_key = section_key
        self.section_data = section_data
        self.config_data = config_data

        edit_btn = discord.ui.Button(label="Edit", style=discord.ButtonStyle.primary)
        edit_btn.callback = self._edit
        self.add_item(edit_btn)

        back_btn = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary)
        back_btn.callback = self._back
        self.add_item(back_btn)

    async def _edit(self, interaction: discord.Interaction) -> None:
        modal = SectionEditModal(self.section_key, self.section_data)
        await interaction.response.send_modal(modal)

    async def _back(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Config Editor",
            description="Select a section to edit.\nChanges are saved immediately.",
            color=discord.Color.blue(),
        )
        view = discord.ui.View(timeout=300)
        view.add_item(ConfigSectionSelect(self.config_data))
        await interaction.response.edit_message(embed=embed, view=view)


class ConfigEditorCog(discord.Cog):
    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot

    @discord.slash_command(
        name="config",
        description="Edit bot configuration via interactive menu.",
    )
    @discord.default_permissions(administrator=True)
    async def config(self, ctx: discord.ApplicationContext) -> None:
        if not os.path.exists(CONFIG_FILE):
            await ctx.respond("Config file not found.", ephemeral=True)
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            await ctx.respond(f"Failed to read config: {e}", ephemeral=True)
            return

        embed = discord.Embed(
            title="Config Editor",
            description="Select a section to edit.\nChanges are saved immediately.",
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Use /config to reopen this menu anytime")
        view = discord.ui.View(timeout=300)
        view.add_item(ConfigSectionSelect(data))
        await ctx.respond(embed=embed, view=view)

    @config.error
    async def config_error(
        self,
        ctx: discord.ApplicationContext,
        error: discord.DiscordException,
    ) -> None:
        logger.error("config error: %s", error)
        await ctx.respond(f"Error: {error}", ephemeral=True)

    @discord.Cog.listener()
    async def on_ready(self) -> None:
        logger.info("ConfigEditorCog loaded")


def setup(bot: discord.Bot) -> None:
    bot.add_cog(ConfigEditorCog(bot))
