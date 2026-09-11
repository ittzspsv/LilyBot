import discord
from discord import app_commands

from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.management.controller import lily_management_controller as controller


class StaffRoleCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="staff_role", description="Staff Management role utility commands")

    @app_commands.command(name="remove", description="Removes a staff role from the database")
    @app_permission(command_name="staff_role_remove")
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, role: discord.Role):
        await controller.remove_role(interaction, role.id)

    @app_commands.command(name="remove_raw", description="Removes a staff role from the database")
    @app_permission(command_name="staff_role_remove_raw")
    @app_commands.guild_only()
    async def remove_raw(self, interaction: discord.Interaction, role: str):
        await controller.remove_role(interaction, int(role))
