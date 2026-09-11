import discord
from discord import app_commands

from src.core.utils.components.sLIlyGlobalComponents import CommandInfo
from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.moderation.controller.lily_moderation_controller import (
    mod_logs,
    case_edit as case_edit_fn,
    case_delete as case_delete_fn,
)
from ..types import ModType


class CaseCommands(app_commands.Group):
    """/case ..."""

    def __init__(self):
        super().__init__(name="case", description="Case management commands")

    @app_commands.command(name='list', description='Checks case logs for a particular user')
    @app_permission(command_name="modlogs")
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

    @app_commands.command(name='edit', description='Edit a case')
    @app_permission(command_name="case_edit")
    async def edit(self, interaction: discord.Interaction, case_id: str, *, new_reason: str):
        if case_id is None or new_reason is None:
            return await interaction.response.send_message(
                view=CommandInfo(interaction, "Case Edit", ["edit_case case_id new_reason"])
            )

        await case_edit_fn(interaction, int(case_id), new_reason, False)

    @app_commands.command(name='edit_absolute', description='Edit any case')
    @app_permission(command_name="case_edit_absolute")
    async def edit_absolute(self, interaction: discord.Interaction, case_id: int, *, new_reason: str):
        await case_edit_fn(interaction, case_id, new_reason, True)

    @app_commands.command(name='delete', description='Delete a case')
    @app_permission(command_name="case_delete")
    async def delete(self, interaction: discord.Interaction, case_id: str):
        await case_delete_fn(interaction, int(case_id))
