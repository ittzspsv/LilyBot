import discord
from discord import app_commands

from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.management.controller import lily_management_controller as controller
from ..autocomplete import timezone_autocomplete


class StaffCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="staff", description="Staff management commands")

    @app_commands.command(name='data', description='shows data for a particular staff')
    @app_permission(command_name="staff_data")
    @app_commands.guild_only()
    async def data(self, interaction: discord.Interaction, user: discord.Member | discord.User | None = None):
        if not user:
            user = interaction.user
        await controller.fetch_staff_detail(interaction, user)

    @app_commands.command(name='list', description='shows all staff registered name with the count')
    @app_permission(command_name="staff_list")
    @app_commands.guild_only()
    async def list(self, interaction: discord.Interaction):
        await controller.fetch_all_staffs(interaction)

    @app_commands.command(name='edit', description='edits a staff data')
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    @app_permission(command_name="staff_edit")
    @app_commands.guild_only()
    async def edit(
        self,
        interaction: discord.Interaction,
        staff: discord.Member | discord.User,
        name: str,
        joined_on: str | None = None,
        timezone: str | None = None,
        responsibility: str | None = None,
    ):
        await controller.edit_staff(interaction, staff.id, name, joined_on, timezone, responsibility)

    @app_commands.command(name="self_edit", description="edits your staff data")
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    @app_permission(command_name="staff_self_edit")
    @app_commands.guild_only()
    async def self_edit(self, interaction: discord.Interaction, name: str, timezone: str | None = None):
        await controller.edit_staff(interaction, interaction.user.id, name, None, timezone, None)

    @app_commands.command(name='add', description='Adds a member to staff_data')
    @app_permission(command_name="staff_add")
    @app_commands.guild_only()
    async def add(self, interaction: discord.Interaction, staff: discord.Member, rank: discord.Role | None = None):
        await controller.add_staff(interaction, staff)

    @app_commands.command(name='remove', description='Removes a member from staff_data')
    @app_permission(command_name="staff_remove")
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, staff: discord.Member | discord.User, reason: str):
        await controller.remove_staff(interaction, staff, reason)

    @app_commands.command(name='roles', description='Returns all staff roles')
    @app_permission(command_name="staff_roles")
    @app_commands.guild_only()
    async def roles(self, interaction: discord.Interaction):
        await controller.get_all_staff_roles(interaction)

    @app_commands.command(name="coverage", description="get the timezone coverage of all the staffs")
    @app_permission(command_name="staff_coverage")
    @app_commands.guild_only()
    async def coverage(self, interaction: discord.Interaction):
        await controller.get_staffs_timezone_coverage(interaction)
