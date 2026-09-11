import discord
from discord import app_commands

from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.management.controller import lily_management_controller as controller


class InfractionCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="infraction", description="Infraction management commands")

    @app_commands.command(name='issue', description='Issue an infraction')
    @app_permission(command_name="strike_add")
    @app_commands.guild_only()
    async def issue(self, interaction: discord.Interaction, staff: discord.Member):
        await controller.strike_staff(interaction, staff)

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
