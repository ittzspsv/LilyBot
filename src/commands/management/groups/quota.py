import discord
from discord import app_commands

from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.management.types.staff_management_types import QuotaCheckBy
from src.core.features.management.controller import lily_management_controller as controller


class QuotaCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="quota", description="Quota management commands")

    @app_commands.command(name="add", description="Adds a staff quota to check by")
    @app_permission(command_name="quota_add")
    @app_commands.guild_only()
    async def add(
        self,
        interaction: discord.Interaction,
        quota_role: discord.Role,
        minimum_ms: int,
        minimum_msg: int,
        check_by: QuotaCheckBy,
    ):
        await controller.add_staff_quota(interaction, quota_role, minimum_ms, minimum_msg, check_by)

    @app_commands.command(name="list", description="List all defined quotas for this server")
    @app_permission(command_name="quota_list")
    @app_commands.guild_only()
    async def list(self, interaction: discord.Interaction):
        await controller.fetch_staff_quota(interaction)

    @app_commands.command(name="remove", description="Remove a defined quota by its ID")
    @app_permission(command_name="quota_remove")
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, quota_id: str):
        await controller.remove_staff_quota(interaction, quota_id)

    @app_commands.command(name="check", description="Check quota for a given staff")
    @app_permission(command_name="quota_check")
    @app_commands.guild_only()
    async def check(self, interaction: discord.Interaction, staff: discord.Member | None = None):
        staff_member = staff or interaction.user
        await controller.check_staff_quota(interaction, staff_member)

    @app_commands.command(name="evaluate", description="Evaluates Staff quota and updates the results")
    @app_permission(command_name="quota_evaluate")
    @app_commands.guild_only()
    async def evaluate(self, interaction: discord.Interaction, role: discord.Role):
        await controller.evaluate_staff_quota(interaction, role)
