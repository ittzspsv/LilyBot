from __future__ import annotations

import discord
from discord import app_commands

from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.management.controller import lily_management_controller as controller

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from src.lily import Lily

async def issue_type_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None
    assert interaction.guild is not None

    strike_types = await bot_db.get_strike_types(interaction.guild.id)

    choices = [
        app_commands.Choice(name="Strike", value="strike"),
        app_commands.Choice(name="Warning", value="warning"),
    ]

    choices.extend(
        app_commands.Choice(
            name=strike_type.title(),
            value=strike_type,
        )
        for strike_type in strike_types
        if strike_type not in {"strike", "warning"}
    )

    return [
        choice
        for choice in choices
        if current.lower() in choice.name.lower()
    ][:25]

async def issue_expiry_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    suggestions = ["1d", "3d", "7d", "14d", "22d", "30d", "none"]
    if not current:
        return [app_commands.Choice(name=s, value=s) for s in suggestions]
    return [
        app_commands.Choice(name=s, value=s)
        for s in suggestions
        if current.lower() in s.lower()
    ][:25]


class InfractionCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="infraction", description="Infraction management commands")


    @app_commands.command(name='issue', description='Issue an infraction')
    @app_permission(command_name="strike_add")
    @app_commands.guild_only()
    @app_commands.describe(
        staff="The staff member to issue the infraction to",
        reason="Reason for the infraction",
        type="The type of infraction (strike or warning or your own type)",
        notify_staff="Whether to notify the staff member via DM",
        notify_staff_updates="Whether to post this infraction to the staff-updates channel",
        expire_after="When this infraction should expire (e.g., 1d, 22d, none)"
    )
    @app_commands.autocomplete(type=issue_type_autocomplete)
    @app_commands.autocomplete(expire_after=issue_expiry_autocomplete)
    async def issue(
        self,
        interaction: discord.Interaction,
        staff: discord.Member,
        reason: str,
        type: str,
        notify_staff: bool = True,
        notify_staff_updates: bool = True,
        expire_after: str = "none"
    ):    
        await controller.strike_staff(interaction, staff, reason, type, notify_staff, notify_staff_updates, expire_after)

    @app_commands.command(name='remove', description='Remove an infraction')
    @app_permission(command_name="strike_remove")
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, infraction_id: str):
        await controller.remove_strike_staff(interaction, int(infraction_id))

    @app_commands.command(name="edit", description="Edit a reason of a infraction")
    @app_permission(command_name="strike_edit")
    @app_commands.guild_only()
    async def edit(self, interaction: discord.Interaction, infraction_id: str, new_reason: str):
        await controller.edit_strike(interaction, int(infraction_id), new_reason)

    @app_commands.command(name='show', description='shows infractions for a concurrent staff')
    @app_permission(command_name="strike_show")
    @app_commands.guild_only()
    async def show(self, interaction: discord.Interaction, staff: discord.Member):
        await controller.list_strikes(interaction, staff)
