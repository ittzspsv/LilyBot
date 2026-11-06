from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Literal,
    Optional,
    Sequence,
    TypeAlias,
    Union,
    cast,
)

import aiohttp
import discord

from src.core.configs.bot_details import emoji, img
from src.core.features.moderation.components.lily_moderation_components import AppealButton

from .event_dispatcher import EventPayload, Events, event

if TYPE_CHECKING:
    from src.lily import Lily

logger = logging.getLogger("lily")

ModerationType: TypeAlias = Literal[
    "ban", "warn", "mute", "quarantine",
    "unmute", "quarantine_release", "unban"
]

_ACTION_TITLES: dict[str, str] = {
        "ban": "You Have Been Banned!",
        "mute": "You Have Been Muted!",
        "quarantine": "You Have Been Quarantined!",
        "warn": "You Have Been Warned!",
        "unban": "You Have Been Unbanned!",
        "unmute": "You Have Been Unmuted!",
        "quarantine_release": "You Have Been Released From Quarantine!",
    }

@dataclass(frozen=True, slots=True)
class ModerationAction:
    case_id: int
    type: ModerationType
    user: discord.Member | discord.User
    target: discord.Member | discord.User
    reason: Optional[str]
    proofs: Optional[Sequence[Union[discord.Attachment, str]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
_APPEALABLE = ("ban", "mute", "quarantine", "warn")

@event(name=Events.MODERATION_ACTION.value)
async def dm_moderation_target(payload: EventPayload, action: ModerationAction) -> None:
    try:
        view = discord.utils.MISSING
        if action.type in _APPEALABLE:
            view = discord.ui.View(timeout=None)
            view.add_item(AppealButton(action.case_id))

        title = _ACTION_TITLES.get(action.type)
        if title is None:
            raise ValueError(f"Unknown action '{action.type}'. Must be one of {list(_ACTION_TITLES)}.")
    
        embed = discord.Embed(color=0xFFFFFF, title=f"{emoji['arrow']} {title}")
    
        if action.type == "warn":
            embed.set_thumbnail(url=img["warn"])
        else:
            embed.set_image(url=img["border"])
    
        embed.add_field(
            name=f"{emoji['bookmark']} Reason",
            value=(action.reason or "No reason provided")[:1024],
            inline=False,
        )
        embed.add_field(name=f"{emoji['bot']} Server", value=payload.guild.name, inline=False)
        await action.target.send(
            embed=embed,
            view=view,
        )
    except discord.HTTPException:
        logger.debug("Could not DM %s about %s (case %s)", action.target.id, action.type, action.case_id)

@event(name=Events.MODERATION_ACTION.value)
async def log_moderation_to_channel(payload: EventPayload, action: ModerationAction) -> None:
    bot = cast("Lily", payload.bot)
    guild = payload.guild
    assert bot.db is not None
    db = bot.db

    logs_channel_id = db.get_channel(guild.id, "logs_channel")
    if not logs_channel_id:
        return

    channel = guild.get_channel(logs_channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(logs_channel_id)
        except discord.HTTPException:
            return

    if not isinstance(channel, discord.TextChannel):
        return

    target, moderator, case_id = action.target, action.user, action.case_id

    try:
        embed = discord.Embed(
            color=0xFFFFFF,
            title=f"{emoji['ticket']} Logging Information",
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name=f"{emoji['bookmark']} Case Type", value=action.type.replace("_", " ").title(), inline=True)
        embed.add_field(name=f"{emoji['member']} User", value=f"<@{target.id}>", inline=True)
        embed.add_field(name=f"{emoji['shield']} Moderator", value=f"<@{moderator.id}>", inline=True)
        embed.add_field(name=f"{emoji['pencil']} Reason", value=(action.reason or "No reason Provided")[:1024], inline=False)
        embed.set_image(url=img["border"])

        await channel.send(
            content=target.mention,
            embeds=[embed],
        )
    except discord.HTTPException:
        logger.exception("Failed to post case %s to logs channel %s", case_id, channel.id)
        return

    if not action.proofs:
        return

    files: list[discord.File] = []
    failed_proofs: list[str] = []

    for proof in action.proofs:
        if isinstance(proof, discord.Attachment):
            try:
                data = await proof.read()
            except discord.HTTPException as e:
                logger.warning("Failed to read attachment %s for case %s: %s", proof.filename, case_id, e)
                failed_proofs.append(proof.filename)
                continue
            files.append(discord.File(io.BytesIO(data), filename=proof.filename))
            continue

        try:
            data = await asyncio.wait_for(bot.http.get_from_cdn(proof), timeout=15)
        except (discord.HTTPException, aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("Failed to fetch proof %s for case %s: %s", proof, case_id, e)
            failed_proofs.append(proof)
            continue

        filename = proof.split("?")[0].split("/")[-1]
        if not filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            filename += ".png"
        files.append(discord.File(io.BytesIO(data), filename=filename))

    if files:
        try:
            message = await channel.send(content=f"Proofs {target.mention}", files=files)
            await db.log_proof_action(guild.id, case_id, message.id, moderator.id)
        except discord.HTTPException:
            logger.exception("Failed to upload proofs for case %s", case_id)
            failed_proofs.extend(f.filename for f in files)

    if failed_proofs:
        await channel.send(
            content=f"{len(failed_proofs)} proof(s) could not be fetched (link expired or inaccessible)."
        )