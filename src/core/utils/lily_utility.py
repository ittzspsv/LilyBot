from __future__ import annotations

from typing import Union, Optional, cast, TYPE_CHECKING, Tuple
import os
import json

from datetime import datetime, timezone
from typing import Optional

import discord
import logging
from discord.ext import commands

if TYPE_CHECKING:
    from src.lily import Lily


logger = logging.getLogger("lily")

# Constants
UTC = timezone.utc


def format_currency(val: Union[str, int]) -> str:
    value = int(val)
    if value >= 1_000_000_000_000_000_000_000_000_000_000_000:  
        return f"{value / 1_000_000_000_000_000_000_000_000_000_000_000:.1f}DX"
    elif value >= 1_000_000_000_000_000_000_000_000_000_000:  
        return f"{value / 1_000_000_000_000_000_000_000_000_000_000:.1f}NX"
    elif value >= 1_000_000_000_000_000_000_000_000_000:  
        return f"{value / 1_000_000_000_000_000_000_000_000_000:.1f}OX"
    elif value >= 1_000_000_000_000_000_000_000_000:  
        return f"{value / 1_000_000_000_000_000_000_000_000:.1f}SPX"
    elif value >= 1_000_000_000_000_000_000_000: 
        return f"{value / 1_000_000_000_000_000_000_000:.1f}SX"
    elif value >= 1_000_000_000_000_000_000:  
        return f"{value / 1_000_000_000_000_000_000:.1f}QI"
    elif value >= 1_000_000_000_000_000:  
        return f"{value / 1_000_000_000_000_000:.1f}QT"
    elif value >= 1_000_000_000_000: 
        return f"{value / 1_000_000_000_000:.1f}T"
    elif value >= 1_000_000_000:  
        return f"{value / 1_000_000_000:.1f}B"
    elif value >= 1_000_000:  
        return f"{value / 1_000_000:.1f}M"
    elif value >= 1_000:  
        return f"{value / 1_000:.1f}k"
    else:
        return str(int(value))


def format_duration(seconds: int | float) -> str:
    units = [
        ("month", 30 * 24 * 60 * 60),
        ("week", 7 * 24 * 60 * 60),
        ("day", 24 * 60 * 60),
        ("hour", 60 * 60),
        ("minute", 60),
        ("second", 1),
    ]

    for name, unit_seconds in units:
        if seconds >= unit_seconds:
            value = seconds / unit_seconds
            return f"{value:.1f} {name}{'s' if value != 1 else ''}"

    return "0 seconds"
    
# function used to safely load an json
def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except (json.JSONDecodeError, OSError):
        return {}
    
# returns current time based on ust
def utcnow() -> datetime:
    return datetime.now(UTC)

def parse_date(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    return datetime.fromisoformat(ts)

def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat()


def proper_capatilize(text):
    return " ".join(word[:1].upper() + word[1:] for word in text.split())

async def change_nickname(
    actor: discord.Member,
    bot_member: discord.Member,
    member: discord.Member,
    name: str | None
) -> str | None:
    if member != actor and actor.top_role <= member.top_role:
        return "You cannot act on this user their role is higher than or equal to yours."

    if member.top_role >= bot_member.top_role:
        return "I can't change that member's nickname their top role is higher or equal to mine."

    if name is not None and len(name) > 32:
        return "Nicknames cannot be longer than 32 characters."

    try:
        await member.edit(
            nick=name,
            reason=f"Changed by {actor}"
        )
        return None

    except discord.Forbidden:
        return "I don't have permission to change that member's nickname."

async def fetch_json(session, url, method="GET", **kwargs):
    async with session.request(method, url, **kwargs) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise Exception(f"HTTP {resp.status}: {text}")
        return await resp.json()


def length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2

def truncate(text: str, limit: int = 1024) -> str:
    suffix = "\n[...]"

    if length(text) <= limit:
        return text

    suffix_length = length(suffix)
    max_text_length = limit - suffix_length

    encoded = text.encode("utf-16-le")
    truncated = encoded[:max_text_length * 2]

    return truncated.decode("utf-16-le", errors="ignore") + suffix

async def purge_messages_by_user(
    interaction: discord.Interaction,
    user: discord.Member,
) -> Tuple[int, int]:
    limit = 500
    adb = cast("Lily", interaction.client).adb
    assert adb is not None

    guild = interaction.guild
    invoker = interaction.user
    assert guild is not None and isinstance(invoker, discord.Member)

    await interaction.response.defer(ephemeral=True)

    batches = await adb.get_user_message_ids(guild.id, user.id, limit)

    deleted = 0
    skipped = 0
    for channel_id, ids in batches.items():
        channel = guild.get_channel_or_thread(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            skipped += 1
            continue

        if not (
            channel.permissions_for(invoker).manage_messages
            and channel.permissions_for(guild.me).manage_messages
        ):
            skipped += 1
            continue

        for i in range(0, len(ids), 100):
            chunk = ids[i : i + 100]
            if len(chunk) < 2:
                break
            try:
                await channel.delete_messages(
                    [discord.Object(id=m) for m in chunk]
                )
            except discord.NotFound:
                break
            except discord.HTTPException:
                logger.exception(
                    "bulk delete failed in channel %s",
                    channel_id,
                )
                break
            await adb.remove_messages(chunk)
            deleted += len(chunk)

    

    return (deleted, skipped)