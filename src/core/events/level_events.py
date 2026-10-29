from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord

from .event_dispatcher import EventPayload, event

if TYPE_CHECKING:
    from src.lily import Lily


@event
async def on_level_up(
    payload: EventPayload,
    user: discord.Member,
    new_level: int,
    roles_awarded: list[discord.Role],
) -> None:
    bot = cast("Lily", payload.bot)

    assert bot.db is not None, "Database is not initialized"

    channel_id = bot.db.get_channel(
        guild_id=payload.guild.id,
        channel_name="leveling_notification",
    )

    if channel_id is None:
        return

    channel = payload.guild.get_channel(channel_id)

    if not isinstance(channel, discord.TextChannel):
        return

    content = (
        f"Congratulations {user.mention}! "
        f"You have leveled up to {new_level}."
    )

    if roles_awarded:
        role_mentions = ", ".join(role.mention for role in roles_awarded)
        content += f"\nRoles awarded: {role_mentions}"

    try:
        await channel.send(
            content=content,
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
            ),
        )
    except discord.HTTPException:
        raise