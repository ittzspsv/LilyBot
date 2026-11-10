import discord
from discord import app_commands

from src.core.utils.components.sLIlyGlobalComponents import CommandInfo
from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.moderation.controller.lily_moderation_controller import (
    mod_logs
)
from ..types import ModType


class CaseCommands(app_commands.Group):
    """/case ..."""

    def __init__(self):
        super().__init__(name="case", description="Case management commands")

    @app_commands.command(name='list', description='Checks case logs for a particular user')
    @app_commands.describe(
        member="The user whose cases you want to see (defaults to you)",
        mod_type="Only show this type of case",
        moderator="Only show cases handled by this moderator"
    )
    @app_permission(
        command_name="modlogs",
        permissions={"moderate_members", "kick_members", "ban_members"},
        match="any",
    )
    async def list(
        self,
        interaction: discord.Interaction,
        member: discord.User | discord.Member | None = None,
        mod_type: ModType = ModType.All,
        moderator: discord.User | discord.Member | None = None
    ):
        target_id = member.id if member else interaction.user.id

        try:
            user = await interaction.client.fetch_user(target_id)
        except Exception:
            return

        try:
            await mod_logs(
                interaction,
                user=user,
                moderator=moderator,
                mod_type=mod_type.value
            )

        except Exception as e:
            print(f"Exception [ModLogs] : {e}")