from __future__ import annotations

from typing import TYPE_CHECKING, cast, List, Literal

import discord

from .event_dispatcher import EventPayload, event

if TYPE_CHECKING:
    from src.lily import Lily


@event
async def on_staff_added(
    payload: EventPayload, 
    member: discord.Member,
    added_by: discord.Member,
    assigned_roles: List[discord.Role]
) -> None:
    ...


@event
async def on_staff_removed(
    payload: EventPayload,
    staff: discord.Member,
    removed_by: discord.Member,
    reason: str,
    removed_roles: List[discord.Role]
) -> None:
    ...

@event
async def on_staff_update(
    payload: EventPayload,
    staff: discord.Member,
    updated_by: discord.Member,
    update_type: Literal["promotion", "demotion"],
    reason: str,
    old_role: discord.Role | None,
    new_role: discord.Role | None,
    elevated: bool,
) -> None:
    ...