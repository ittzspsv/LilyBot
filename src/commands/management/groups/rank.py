import discord
from discord import app_commands

from src.core.features.permissions.lily_permissions import app_permission
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.features.management.components.staff_management_components import RankConfigureModal
from src.core.features.management.controller import lily_management_controller as controller


class RankCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="rank", description="Promotion and demotion commands")

    @app_commands.command(name='promote', description='Promotes a staff to upper rank')
    @app_permission(command_name="rank_promote")
    @app_commands.guild_only()
    async def promote(
        self,
        interaction: discord.Interaction,
        staff: discord.Member,
        *,
        reason: str,
        rank: discord.Role | None = None,
    ):
        await controller.update_staff(interaction, staff, reason, "promotion", rank=rank)

    @app_commands.command(name='demote', description='Demotes a staff to lower rank')
    @app_permission(command_name="rank_demote")
    @app_commands.guild_only()
    async def demote(
        self,
        interaction: discord.Interaction,
        staff: discord.Member,
        *,
        reason: str,
        rank: discord.Role | None = None,
    ):
        await controller.update_staff(interaction, staff, reason, "demotion", rank=rank)

    @app_commands.command(name="configure", description="Configure staff ranks")
    @app_permission(command_name="rank_configure")
    @app_commands.guild_only()
    async def configure(self, interaction: discord.Interaction):
        bot_db: BotGlobalsDatabaseAccess = interaction.client.db

        assert interaction.guild is not None

        try:
            staff_ranks = await bot_db.get_staff_ranks(interaction.guild.id)
            await interaction.response.send_modal(
                RankConfigureModal(bot_db, staff_ranks)
            )
        except Exception as e:
            print(e)
