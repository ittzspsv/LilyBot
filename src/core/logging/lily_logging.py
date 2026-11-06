from __future__ import annotations

from ..database.integrations.bot_globals import BotGlobalsDatabaseAccess

from discord.ext import commands
from datetime import datetime
from typing import Optional, Union, Sequence, List, Dict, Any, cast, TYPE_CHECKING
from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.utils.lily_utility import utcnow
from .components.logging_components import ProofComponentModal
from src.core.events.event_dispatcher import EventPayload, Events
from src.core.events.moderation_events import ModerationAction, ModerationType

import discord
import io
import re
import logging

if TYPE_CHECKING:
    from src.lily import Lily

logger = logging.getLogger("lily")


class LilyLoggingController:
    def __init__(self, bot_db: BotGlobalsDatabaseAccess) -> None:
        self.bot_db = bot_db

    async def log_moderation_action(
        self,
        ctx: commands.Context | discord.Interaction,
        moderator: discord.Member | discord.User,
        target_user: discord.Member | discord.User,
        mod_type: ModerationType,
        reason: str = "No reason provided",
        proofs: Optional[Sequence[Union[discord.Attachment, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int | None:
        metadata = dict(metadata) if metadata else {}

        guild = ctx.guild
        if guild is None:
            content = "Guild object is required for this command to be executed"
            if isinstance(ctx, commands.Context):
                await ctx.reply(content)
            elif ctx.response.is_done():
                await ctx.followup.send(content)
            else:
                await ctx.response.send_message(content)
            return None

        bot = cast("Lily", ctx.client if isinstance(ctx, discord.Interaction) else ctx.bot)

        acronyms: dict[str, str] = await self.bot_db.get_moderation_acronyms(moderator.id, guild.id)
        reason = re.sub(
            r"\b\w+\b",
            lambda m: acronyms.get(m.group(0).lower(), m.group(0)),
            reason,
        )

        if isinstance(ctx, commands.Context):
            metadata["command_message_reference"] = [ctx.channel.id, ctx.message.id]

        modlog = await self.bot_db.log_moderation_action(
            guild.id, moderator.id, target_user.id, mod_type, reason, metadata
        )

        if modlog is not None:
            await bot.events.invoke(
                name=Events.MODERATION_ACTION.value,
                payload=EventPayload(bot=bot, guild=guild),
                action=ModerationAction(
                    case_id=modlog.id,
                    type=mod_type,
                    user=moderator,
                    target=target_user,
                    reason=reason,
                    proofs=proofs,
                    metadata=metadata,
                )
            )

        return modlog.id

    async def post_log(
        self,
        ctx: commands.Context, 
        embed: discord.Embed, 
        log_type:str="Default Log Type"
    ) -> None:
        if ctx.guild is None:
            content = "Guild object is required for this command to be executed"
            if isinstance(ctx, commands.Context):
                await ctx.reply(content)
            elif isinstance(ctx, discord.Interaction):
                if ctx.response.is_done():
                    await ctx.followup.send(content)
                else:
                    await ctx.response.send_message(content)

            return
        logs_channel = self.bot_db.get_channel(ctx.guild.id, "logs_channel")

        if not logs_channel:
            return

        channel = ctx.guild.get_channel(logs_channel)

        if channel is None:
            try:
                channel = await ctx.guild.fetch_channel(logs_channel)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return

        if isinstance(channel, discord.TextChannel):
            await channel.send(
                content=str(log_type),
                embeds=[embed]
            )

    async def send_proofs(
        self,
        interaction: discord.Interaction,
        proofs: List[discord.Attachment],
        case_id: int
    ) -> bool:
        if interaction.guild is None:
            return False
        
        case = await self.bot_db.get_case(case_id, interaction.guild.id)
        if not case:
            return False

        logs_channel_id = self.bot_db.get_channel(interaction.guild.id, "logs_channel")
        if not logs_channel_id:
            return False
        
        channel = interaction.guild.get_channel(logs_channel_id)

        if channel is None:
            try:
                channel = await interaction.guild.fetch_channel(logs_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return False
        
        if proofs and case_id and isinstance(channel, discord.TextChannel):
            files: List[discord.File] = []
            for proof in proofs:
                if isinstance(proof, discord.Attachment):
                    data = await proof.read()
                    file = discord.File(
                            fp=io.BytesIO(data),
                            filename=proof.filename
                        )
                    files.append(file)
                else:
                    continue
            """ Send the proofs to the logging channel """
            message = await channel.send(
                content=f"Proofs #case-{case_id}\n-by {interaction.user.id}",
                files=files
            )

            """ Store the message id on the database for future retrieval """
            await self.bot_db.log_proof_action(interaction.guild.id, case_id, message.id, interaction.user.id)

            return True
        else:
            return False
        
    async def retrieve_proofs(
        self,
        interaction: discord.Interaction,
        case_id: int
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=simple_embed(
                    "This command can only be executed inside a server.",
                    "cross"
                )
            )
            return

        """ Check the validity of the case """
        case = await self.bot_db.get_case(case_id, interaction.guild.id)
        if not case:
            await interaction.response.send_message(
                embed=simple_embed(
                    "Case doesn't exists!",
                    "cross"
                )
            )
            return

        message_ids = await self.bot_db.get_proof_references(case_id)

        if not message_ids:
            await interaction.response.send_message(
                embed=simple_embed(
                    "No proofs found for the given case ID.",
                    "cross"
                )
            )
            return

        logs_channel_id = self.bot_db.get_channel(interaction.guild.id, "logs_channel")

        if not logs_channel_id:
            await interaction.response.send_message(
                embed=simple_embed(
                    "Proofs cannot be retrieved: logging channel is not configured.",
                    "cross"
                )
            )
            return

        channel = interaction.guild.get_channel(logs_channel_id)

        if channel is None:
            try:
                channel = await interaction.guild.fetch_channel(logs_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                await interaction.response.send_message(
                    embed=simple_embed(
                        "Proofs cannot be retrieved: logging channel is missing or inaccessible.",
                        "cross"
                    )
                )
                return
            
        if not isinstance(channel, discord.TextChannel):
            return

        files: list[discord.File] = []

        for message_id in message_ids:
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                continue
            except discord.Forbidden:
                await interaction.response.send_message(
                    embed=simple_embed(
                        "Missing permission to read messages in the logging channel.",
                        "cross"
                    )
                )
                return
            except discord.HTTPException:
                continue

            for attachment in message.attachments:
                try:
                    data = await attachment.read()
                    files.append(
                        discord.File(
                            fp=io.BytesIO(data),
                            filename=attachment.filename
                        )
                    )
                except discord.HTTPException:
                    continue

        if not files:
            await interaction.response.send_message(
                embed=simple_embed(
                    "No valid proof attachments were found for this case.",
                    "cross"
                )
            )
            return

        await interaction.response.send_message(
            content=f"Proofs for case `{case_id}`",
            files=files
        )

    async def log_proofs(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return
        modal = ProofComponentModal()
        await interaction.response.send_modal(modal)