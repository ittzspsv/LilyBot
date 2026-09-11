import discord
from discord import app_commands

from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.management.controller import lily_management_controller as controller


class LoaCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="loa", description="Leave of absence management")

    @app_commands.command(name='add', description='Assigns a staff leave')
    @app_permission(command_name="loa_add")
    @app_commands.guild_only()
    async def add(self, interaction: discord.Interaction, staff: discord.Member, *, reason: str):
        await controller.add_loa(interaction, staff, reason)

    @app_commands.command(name='delete', description='Delete an LOA entry from the database')
    @app_permission(command_name="loa_delete")
    @app_commands.guild_only()
    async def delete(self, interaction: discord.Interaction, leave_id: int):
        await controller.loa_delete(interaction, leave_id)

    @app_commands.command(name='remove', description='Removes a staff leave')
    @app_permission(command_name="loa_remove")
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, staff: discord.Member):
        await controller.remove_loa(interaction, staff)

    @app_commands.command(name="show", description="List all LOA for a particular staff")
    @app_permission(command_name="loa_show")
    @app_commands.guild_only()
    async def show(self, interaction: discord.Interaction, staff: discord.Member | None = None):
        if staff is None:
            current_staff = interaction.user
        else:
            current_staff = staff

        if isinstance(current_staff, discord.Member):
            await controller.list_loa(interaction, current_staff)

    @app_commands.command(name="request", description="Request LOA")
    @app_permission(command_name="loa_request")
    @app_commands.guild_only()
    async def request(self, interaction: discord.Interaction):
        await controller.request_loa(interaction)
