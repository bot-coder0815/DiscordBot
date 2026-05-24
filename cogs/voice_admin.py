import asyncio
import datetime
from typing import Optional

import discord

from services.logging.logger import setup_logger

logger = setup_logger("voice_admin")

FORCE_MUTED: dict[int, dict[str, bool]] = {}
VOTE_LOCKS: set[int] = set()


class VoteOutView(discord.ui.View):
    def __init__(
        self, target: discord.Member, requester: discord.Member, cog: "VoiceAdminCog"
    ) -> None:
        super().__init__(timeout=300)
        self.target = target
        self.requester = requester
        self.cog = cog
        self.votes_yes: set[int] = set()
        self.votes_no: set[int] = set()
        self._message: Optional[discord.Message] = None

    async def on_timeout(self) -> None:
        await self._finish_vote()

    async def _finish_vote(self) -> None:
        VOTE_LOCKS.discard(self.target.id)
        yes = len(self.votes_yes)
        no = len(self.votes_no)

        if yes > no:
            until = discord.utils.utcnow() + datetime.timedelta(minutes=10)
            try:
                await self.target.timeout(
                    until, reason=f"Voted out by {self.requester} ({yes}/{no})"
                )
                result = (
                    f"{self.target.mention} wurde für 10 Minuten getimeoutet."
                    f"\n{yes}:yes | {no}:no"
                )
            except Exception as e:
                result = f"Timeout fehlgeschlagen: {e}"
        else:
            result = (
                f"{self.target.mention} bleibt verschont."
                f"\n{yes}:yes | {no}:no"
            )

        if self._message:
            try:
                for child in self.children:
                    child.disabled = True
                embed = self._message.embeds[0]
                embed.color = discord.Color.red() if yes > no else discord.Color.green()
                await self._message.edit(content=result, embed=embed, view=self)
            except Exception:
                pass

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def vote_yes(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        await self._vote(interaction, True)

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def vote_no(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        await self._vote(interaction, False)

    async def _vote(
        self, interaction: discord.Interaction, choice: bool
    ) -> None:
        uid = interaction.user.id

        if uid in (self.votes_yes | self.votes_no):
            await interaction.response.send_message(
                "Du hast bereits abgestimmt.", ephemeral=True
            )
            return

        if choice:
            self.votes_yes.add(uid)
        else:
            self.votes_no.add(uid)

        await interaction.response.send_message(
            f"Abgestimmt: {'Yes' if choice else 'No'}", ephemeral=True
        )

        embed = self._message.embeds[0] if self._message else None
        if embed:
            embed.description = (
                f"**{self.target.mention}**\n\n"
                f":thumbsup: Yes: {len(self.votes_yes)}\n"
                f":thumbsdown: No: {len(self.votes_no)}"
            )
            try:
                await self._message.edit(embed=embed)
            except Exception:
                pass


class VoiceAdminCog(discord.Cog):
    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot

    @discord.slash_command(
        name="forcemute",
        description="Force-mute a user in voice (headphones=deafen, microphone=mute).",
    )
    @discord.default_permissions(move_members=True)
    async def forcemute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        type: str = discord.Option(
            choices=["headphones", "microphone"],
            description="headphones = deafen, microphone = mute",
        ),
    ) -> None:
        if not user.voice or not user.voice.channel:
            await ctx.respond(
                f"{user.mention} ist in keinem Voice-Channel.", ephemeral=True
            )
            return

        if type == "headphones":
            await user.edit(deafen=True)
            entry = FORCE_MUTED.setdefault(user.id, {"mute": False, "deafen": False})
            entry["deafen"] = True
            label = "headphones (deafen)"
        else:
            await user.edit(mute=True)
            entry = FORCE_MUTED.setdefault(user.id, {"mute": False, "deafen": False})
            entry["mute"] = True
            label = "microphone (mute)"

        await ctx.respond(
            f"{user.mention} wurde forcemuted ({label}).", ephemeral=True
        )

    @forcemute.error
    async def forcemute_error(
        self,
        ctx: discord.ApplicationContext,
        error: discord.DiscordException,
    ) -> None:
        logger.error("forcemute error: %s", error)
        await ctx.respond(f"Fehler: {error}", ephemeral=True)

    @discord.slash_command(
        name="unforcemute",
        description="Remove force-mute from a user.",
    )
    @discord.default_permissions(move_members=True)
    async def unforcemute(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
        type: str = discord.Option(
            choices=["headphones", "microphone", "both"],
            description="Which to un-force",
        ),
    ) -> None:
        entry = FORCE_MUTED.get(user.id)
        if not entry:
            await ctx.respond(
                f"{user.mention} ist nicht forcemuted.", ephemeral=True
            )
            return

        if type in ("headphones", "both"):
            entry["deafen"] = False
            try:
                await user.edit(deafen=False)
            except Exception:
                pass

        if type in ("microphone", "both"):
            entry["mute"] = False
            try:
                await user.edit(mute=False)
            except Exception:
                pass

        if not any(entry.values()):
            FORCE_MUTED.pop(user.id, None)

        await ctx.respond(
            f"{user.mention} wurde un-forcemuted ({type}).", ephemeral=True
        )

    @unforcemute.error
    async def unforcemute_error(
        self,
        ctx: discord.ApplicationContext,
        error: discord.DiscordException,
    ) -> None:
        logger.error("unforcemute error: %s", error)
        await ctx.respond(f"Fehler: {error}", ephemeral=True)

    @discord.slash_command(
        name="disconnectall",
        description="Disconnect all members from your current voice channel.",
    )
    @discord.default_permissions(move_members=True)
    async def disconnectall(
        self,
        ctx: discord.ApplicationContext,
    ) -> None:
        author_voice = ctx.author.voice
        if not author_voice or not author_voice.channel:
            await ctx.respond(
                "Du bist in keinem Voice-Channel.", ephemeral=True
            )
            return

        channel = author_voice.channel
        members = [m for m in channel.members if m.id != self.bot.user.id]
        if not members:
            await ctx.respond(
                "Keine anderen Member im Channel.", ephemeral=True
            )
            return

        count = 0
        for m in members:
            try:
                await m.edit(voice_channel=None)
                count += 1
            except Exception as e:
                logger.warning("Failed to disconnect %s: %s", m, e)

        await ctx.respond(
            f"{count} Member wurden aus {channel.mention} disconnected.",
            ephemeral=True,
        )

    @disconnectall.error
    async def disconnectall_error(
        self,
        ctx: discord.ApplicationContext,
        error: discord.DiscordException,
    ) -> None:
        logger.error("disconnectall error: %s", error)
        await ctx.respond(f"Fehler: {error}", ephemeral=True)

    @discord.slash_command(
        name="voteout",
        description="Start a 5-minute vote to timeout a user for 10 minutes.",
    )
    @discord.default_permissions(moderate_members=True)
    async def voteout(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Member,
    ) -> None:
        if ctx.author.id == user.id:
            await ctx.respond(
                "Du kannst nicht gegen dich selbst voten.", ephemeral=True
            )
            return

        if user.id in VOTE_LOCKS:
            await ctx.respond(
                "Es läuft bereits eine Abstimmung für diesen User.",
                ephemeral=True,
            )
            return

        VOTE_LOCKS.add(user.id)

        embed = discord.Embed(
            title="Voteout",
            description=f"**{user.mention}**\n\n:thumbsup: Yes: 0\n:thumbsdown: No: 0",
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Abstimmung läuft 5 Minuten | Ein Vote pro Person")

        view = VoteOutView(target=user, requester=ctx.author, cog=self)

        await ctx.respond(embed=embed, view=view)
        msg = await ctx.interaction.original_response()
        view._message = msg

    @voteout.error
    async def voteout_error(
        self,
        ctx: discord.ApplicationContext,
        error: discord.DiscordException,
    ) -> None:
        logger.error("voteout error: %s", error)
        VOTE_LOCKS.discard(ctx.kwargs.get("user", discord.Object(0)).id)
        await ctx.respond(f"Fehler: {error}", ephemeral=True)

    @discord.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        entry = FORCE_MUTED.get(member.id)
        if not entry:
            return

        if entry["deafen"] and after.self_deaf:
            try:
                await member.edit(deafen=True)
            except Exception:
                pass

        if entry["mute"] and after.self_mute is False:
            try:
                await member.edit(mute=True)
            except Exception:
                pass

    @discord.Cog.listener()
    async def on_ready(self) -> None:
        logger.info("VoiceAdminCog loaded")


def setup(bot: discord.Bot) -> None:
    bot.add_cog(VoiceAdminCog(bot))
