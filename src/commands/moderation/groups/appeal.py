import discord
from discord import app_commands

from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.features.moderation.components.lily_moderation_components import AppealForumCustomize
from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.moderation.controller.lily_moderation_controller import (
    setup_mod_appeal,
    accept_appeal as accept_appeal_fn,
    reject_appeal as reject_appeal_fn,
)


class AppealCommands(app_commands.Group):
    """/appeal ..."""

    def __init__(self):
        super().__init__(name="appeal", description="Moderation appeal commands")

    @app_commands.command(name="setup", description="Setup Moderation Appeal for this server")
    @app_permission(
        command_name="mod_appeal_management",
        permissions={"manage_channels", "manage_webhooks"},
        match="all",
    )
    async def setup(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))
            return
        await setup_mod_appeal(interaction)

    @app_commands.command(
        name="forum",
        description="Configure the appeal forum that users can fill out."
    )
    @app_permission(
        command_name="mod_appeal_management",
        permissions={"manage_guild", "manage_channels"},
        match="any",
    )
    async def forum(
        self,
        interaction: discord.Interaction,
    ):
        if interaction.guild is None:
            return await interaction.response.send_message(
                embed=simple_embed(
                    "This command can only be used inside a guild.",
                    "cross",
                )
            )

        await interaction.response.send_modal(
            AppealForumCustomize(interaction.client.db)
        )
