from __future__ import annotations

from typing import TYPE_CHECKING, cast, Dict, TypeAlias, Literal

import discord

from .event_dispatcher import EventPayload, event

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
    ...

@event
async def on_appeal_handled(
    payload: EventPayload,
    type: AppealType,
    user: discord.User | discord.Member,
    moderator: discord.Member,
    case_id: int,
    reason: str = "No Reason Provided"
) -> None:
    ...