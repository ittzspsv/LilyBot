from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord

from .event_dispatcher import EventPayload, event

if TYPE_CHECKING:
    from src.lily import Lily


@event
async def on_appeal_requested(
    payload: EventPayload,
    user: discord.User,
    case_id: int,
    thread: discord.Thread
) -> None:
    ...

@event
async def on_appeal_handled(
    payload: EventPayload
) -> None:
    ...