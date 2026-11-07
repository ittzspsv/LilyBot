from __future__ import annotations

from typing import TYPE_CHECKING, cast, Dict, TypeAlias, Literal

import discord

from .event_dispatcher import EventPayload, event, Events
from src.core.configs.bot_details import img

if TYPE_CHECKING:
    from src.lily import Lily


AppealType: TypeAlias = Literal["accepted", "rejected"]


@event
async def on_appeal_requested(
    payload: EventPayload,
    user: discord.User,
    case_id: int,
    appeal_response: Dict[str, str],
    thread: discord.Thread
) -> None:
    bot = cast(Lily, payload.bot)

    if not bot.db:
        return

    channel = bot.db.get_channel(
        payload.guild.id,
        Events.APPEAL_REQUESTED.value
    )

    if not channel:
        return

    if not isinstance(channel, discord.TextChannel):
        return

    embed = discord.Embed(
        title="Appeal Requested",
        description=(
            f"{user.mention} has submitted an appeal for "
            f"[Case #{case_id}]({thread.jump_url})."
        ),
        color=0xFFFFFF,
    )

    embed.set_author(
        name=f"{user.name}",
        icon_url=user.display_avatar.url
    )

    for field, value in appeal_response.items():
        embed.add_field(
            name=field.replace("_", " ").title(),
            value=value or "Not provided",
            inline=False
        )

    embed.add_field(
        name="Appeal Thread",
        value=thread.mention,
        inline=False
    )

    embed.set_footer(text=f"Case ID: {case_id}")
    embed.set_image(url=img["border"])

    await channel.send(embed=embed)


@event
async def on_appeal_handled(
    payload: EventPayload,
    type: AppealType,
    user: discord.User | discord.Member,
    moderator: discord.Member,
    case_id: int,
    reason: str = "No Reason Provided"
) -> None:
    bot = cast(Lily, payload.bot)

    if not bot.db:
        return

    channel = bot.db.get_channel(
        payload.guild.id,
        Events.APPEAL_HANDLED.value
    )

    if not channel:
        return

    if not isinstance(channel, discord.TextChannel):
        return

    appeal_type = getattr(type, "value", str(type))

    embed = discord.Embed(
        title="Appeal Handled",
        description=(
            f"The appeal submitted by {user.mention} "
            f"for Case **#{case_id}** has been handled."
        ),
        color=0xFFFFFF,
    )

    embed.set_author(
        name=f"{moderator} ({moderator.id})",
        icon_url=moderator.display_avatar.url
    )

    embed.add_field(
        name="Appeal Status",
        value=str(appeal_type).replace("_", " ").title(),
        inline=True
    )

    embed.add_field(
        name="Appealed By",
        value=f"{user.mention}\n`{user.id}`",
        inline=True
    )

    embed.add_field(
        name="Moderator",
        value=f"{moderator.mention}",
        inline=True
    )

    embed.add_field(
        name="Reason",
        value=reason or "No Reason Provided",
        inline=False
    )

    embed.set_footer(text=f"Case ID: {case_id}")
    embed.set_image(url=img["border"])


    await channel.send(embed=embed)