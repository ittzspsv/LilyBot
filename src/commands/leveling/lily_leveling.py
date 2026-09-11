from discord.ext import commands
from discord import app_commands

from src.core.features.leveling.controller.lily_leveling_controller import show_level


import discord


class LilyLeveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="level", description="Displays your current level")
    @app_commands.guild_only()
    async def show_level(self, interaction: discord.Interaction, member: discord.Member | None):
        assert interaction.guild is not None
        _member = member if member is not None else interaction.user
        await show_level(interaction, _member)

async def setup(bot):
    cog = LilyLeveling(bot)
    await bot.add_cog(cog)