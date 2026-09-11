import discord
from discord import app_commands

from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.features.moderation.components.lily_moderation_components import ModerationDashboard
from src.core.features.permissions.lily_permissions import app_permission
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.features.moderation.controller.lily_moderation_controller import (
    ms as ms_fn,
    moderation_insights as moderation_insights_fn,
    setup_mod_appeal,
)


class ModCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="mod", description="Moderation Command Hierarchy")

    @app_commands.command(name='stats', description='checks stats for a particular moderator or yourself')
    @app_permission(command_name="ms")
    async def stats(
        self,
        interaction: discord.Interaction,
        member: discord.Member | discord.User | None = None,
        page_start: int = 0,
        page_end: int = 0,
    ):
        user = member or interaction.user

        await ms_fn(
            interaction=interaction,
            moderator=user,
            page_start=page_start,
            page_end=page_end
        )

    @app_commands.command(name='insights', description='Get detailed moderation insights')
    @app_permission(command_name="moderation_insights")
    async def insights(self, interaction: discord.Interaction):
        await moderation_insights_fn(interaction)

    @app_commands.command(name="acronym_add", description="Add an reason acronym")
    @app_permission(command_name="mod_acronym_add")
    async def acronym_add(self, interaction: discord.Interaction, key: str, *, value: str):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))

        bot_db: BotGlobalsDatabaseAccess = interaction.client.db
        await bot_db.add_moderation_acronym(interaction.user.id, interaction.guild.id, key, value)
        await interaction.response.send_message(embed=simple_embed(f"Successfully Added Moderation Acronym"))

    @app_commands.command(name="acronym_remove", description="Removes an reason acronym")
    @app_permission(command_name="mod_acronym_remove")
    async def acronym_remove(self, interaction: discord.Interaction, *, key: str):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))

        bot_db: BotGlobalsDatabaseAccess = interaction.client.db

        await bot_db.remove_moderation_acronym(interaction.user.id, interaction.guild.id, key)
        await interaction.response.send_message(embed=simple_embed(f"Successfully Removed Moderation Acronym"))

    @app_commands.command(name="acronym_update", description="Updates an reason acronym")
    @app_permission(command_name="mod_acronym_update")
    async def acronym_update(self, interaction: discord.Interaction, key: str, *, value: str):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))

        bot_db: BotGlobalsDatabaseAccess = interaction.client.db
        await bot_db.update_moderation_acronym(interaction.user.id, interaction.guild.id, key, value)

        await interaction.response.send_message(embed=simple_embed(f"Successfully Updated Moderation Acronym"))

    @app_commands.command(name="acronyms", description="Display all moderation acronyms")
    @app_permission(command_name="mod_acronyms")
    async def acronyms(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))

        bot_db: BotGlobalsDatabaseAccess = interaction.client.db
        result: dict[str, str] = await bot_db.get_moderation_acronyms(member.id if member is not None else interaction.user.id, interaction.guild.id)

        acronyms_text = ""
        for key, value in result.items():
            acronyms_text += f"- **{key}** : {value}\n"

        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Moderation Acronyms",
            description=acronyms_text,
            color=16777215
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="acronym_transfer", description="Transfer an acronym to a members at a role")
    @app_permission(command_name="mod_acronym_transfer")
    async def acronym_transfer(self, interaction: discord.Interaction, target: discord.Member):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))

        bot_db: BotGlobalsDatabaseAccess = interaction.client.db
        result: dict[str, str] = await bot_db.get_moderation_acronyms(interaction.user.id, interaction.guild.id)

        for key, value in result.items():
            await bot_db.add_moderation_acronym(target.id, interaction.guild.id, key, value)

        await interaction.response.send_message(embed=simple_embed(f"Successfully transferred moderation acronym to {target.mention}"))

    @app_commands.command(name="dashboard", description="Spawn in the dashboard")
    @app_permission(command_name="dashboard", restrict=True)
    async def dashboard(self, interaction: discord.Interaction):
        view = ModerationDashboard({
            "setup_mod_appeal": setup_mod_appeal
        })

        await interaction.response.send_message(
            view=view,
            ephemeral=True
        )
