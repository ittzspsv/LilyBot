from __future__ import annotations

from discord.ext import commands
from discord import app_commands
from typing import cast, TYPE_CHECKING

from src.core.features.leveling.controller.lily_leveling_controller import show_level
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess


import discord
import logging

if TYPE_CHECKING:
    from src.lily import Lily

logger = logging.getLogger("lily")


class LilyLeveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="level", description="Displays your current level")
    @app_commands.guild_only()
    async def show_level(self, interaction: discord.Interaction, member: discord.Member | None):
        assert interaction.guild is not None
        _member = member if member is not None else interaction.user
        await show_level(interaction, _member)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setxpboost(self, ctx: commands.Context, role: discord.Role, multiplier: float):
        if multiplier <= 0:
            return await ctx.send("Multiplier must be positive.")

        if ctx.guild is None:
            await ctx.reply("This command can only be executed inside a guild")
            return

        bot_db = cast("Lily", ctx.bot).db
        assert bot_db is not None
        await bot_db.set_xp_boost(ctx.guild.id, role.id, multiplier)
        await ctx.send(f"{role.mention} now grants {multiplier}x XP.", allowed_mentions=discord.AllowedMentions.none())

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def removexpboost(self, ctx: commands.Context, role: discord.Role):
        if ctx.guild is None:
            await ctx.reply("This command can only be executed inside a guild")
            return

        bot_db = cast("Lily", ctx.bot).db
        assert bot_db is not None

        await bot_db.remove_xp_boost(ctx.guild.id, role.id)
        await ctx.send(f"Removed XP boost from {role.mention}.", allowed_mentions=discord.AllowedMentions.none())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
                return
        
        if isinstance(message.author, discord.User):
            return

        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        try:
            allowed_channels = bot_db.get_channels(message.guild.id, "valid_channel")
            if message.channel.id in allowed_channels:

                member_role_ids = {role.id for role in message.author.roles}
                boosted_roles = await bot_db.fetch_boosted_roles(message.guild.id) # We will cache this in memory in future

                result = await bot_db.update_message(
                    staff_id=message.author.id,
                    guild_id=message.guild.id,
                    member_role_ids=member_role_ids,
                    boosted_roles=boosted_roles,
                    avatar_url=message.author.display_avatar.url,
                    name=message.author.name,
                )

                if result and result["leveled_up"]:
                    return
                    await message.channel.send(
                        f"🎉 {message.author.mention} leveled up to **level {result['new_level']}**!"
                    )

        except Exception:
            logger.exception(f"[OnMessage] Failed to update message stats for staff_id={message.author.id} in guild_id={message.guild.id}")

async def setup(bot):
    cog = LilyLeveling(bot)
    await bot.add_cog(cog)