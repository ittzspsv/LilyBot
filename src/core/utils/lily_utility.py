from typing import Union, Optional
import os
import json

from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands

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
