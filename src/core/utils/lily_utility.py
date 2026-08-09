from typing import Union, Optional
import os
import json

from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands import MemberConverter

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

async def get_safe_member(*,bot: Optional[commands.Bot],guild: Union[discord.Guild, int], id: int) -> Optional[discord.Member]:
    if isinstance(guild, discord.Guild):
        member = guild.get_member(id)

        if member:
            return member

        try:
            return await guild.fetch_member(id)
        except:
            return None

    guild_obj = bot.get_guild(guild) if bot else None

    if not guild_obj:
        try:
            guild_obj = await bot.fetch_guild(guild)
        except:
            return None

    try:
        return await guild_obj.fetch_member(id)
    except:
        return None
    
async def get_member_from_user(bot, interaction: discord.Interaction, user: Union[int, str]):
    converter = MemberConverter()

    try:
        ctx = await bot.get_context(interaction.message)
        member: Optional[discord.Member] = await converter.convert(ctx, str(user))
        print(member.id)
    except commands.CommandError:
        print("Error Processing the command")

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