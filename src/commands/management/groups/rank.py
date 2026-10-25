from __future__ import annotations

import discord
from discord import app_commands

from src.core.features.permissions.lily_permissions import app_permission
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.features.management.components.staff_management_components import RankConfigureModal, RankUpdateList
from src.core.features.management.controller import lily_management_controller as controller

from typing import cast, TYPE_CHECKING

if TYPE_CHECKING:
    from src.lily import Lily


class RankCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="rank", description="Promotion and demotion commands")

    @app_commands.command(name='promote', description='Promotes a staff to upper rank')
    @app_permission(command_name="rank_promote", permissions={"manage_roles", "manage_guild"})
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
    @app_permission(command_name="rank_demote", permissions={"manage_roles"})      
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
    @app_permission(command_name="rank_configure", permissions={"manage_guild"})
    @app_commands.guild_only()
    async def configure(self, interaction: discord.Interaction):
        bot_db = cast("Lily", interaction.client).db

        assert interaction.guild is not None
        assert bot_db is not None

        try:
            staff_ranks = await bot_db.get_staff_ranks(interaction.guild.id)
            await interaction.response.send_modal(
                RankConfigureModal(bot_db, staff_ranks)
            )
        except Exception as e:
            print(e)


    @app_commands.command(name="history", description="Display the rank update history")
    @app_permission(command_name="rank_history", permissions={"manage_guild"})
    @app_commands.guild_only()
    async def history(self, interaction: discord.Interaction):
        assert interaction.guild is not None

        bot_db = cast("Lily" , interaction.client).db
        assert bot_db is not None

        result = await bot_db.get_rank_updates(interaction.guild.id, page_size=3)
        view = RankUpdateList(
            result,
            thumbnail_url=interaction.guild.icon.url if interaction.guild.icon else interaction.guild.me.display_avatar.url,
        )
        await interaction.response.send_message(
            view=view, allowed_mentions=discord.AllowedMentions.none()
        )