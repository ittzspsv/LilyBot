from __future__ import annotations

from discord.ext import commands
from discord import app_commands
from typing import cast, TYPE_CHECKING

from src.core.features.leveling.controller.lily_leveling_controller import show_level
from src.core.features.permissions.lily_permissions import app_permission
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess


import discord
import logging

if TYPE_CHECKING:
    from src.lily import Lily

logger = logging.getLogger("lily")


class LilyLeveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    booster = app_commands.Group(
        name="xpboost",
        description="Leveling XP Boosting"
    )

    level_roles = app_commands.Group(
        name="levelroles",
        description="Leveling Roles"
    )

    @app_commands.command(name="level", description="Displays your current level")
    @app_commands.guild_only()
    async def show_level(self, interaction: discord.Interaction, member: discord.Member | None):
        assert interaction.guild is not None
        _member = member if member is not None else interaction.user
        await show_level(interaction, _member)

    @booster.command(name="set", description="Set a level booster role")
    @app_permission(command_name="leveling_management")
    async def setxpboost(self, interaction: discord.Interaction, role: discord.Role, multiplier: int):
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be executed inside a guild.",
                ephemeral=True,
            )
            return

        if multiplier <= 0:
            await interaction.response.send_message(
                "Multiplier must be positive.",
                ephemeral=True,
            )
            return

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        await bot_db.set_xp_boost(
            interaction.guild.id,
            role.id,
            multiplier,
        )

        await interaction.response.send_message(
            f"{role.mention} now grants {multiplier}x XP.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @booster.command(name="remove", description="Remove a level booster role")
    @app_permission(command_name="leveling_management")
    async def removexpboost(self, interaction: discord.Interaction, role: discord.Role):
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be executed inside a guild.",
                ephemeral=True,
            )
            return

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        await bot_db.remove_xp_boost(
            interaction.guild.id,
            role.id,
        )

        await interaction.response.send_message(
            f"Removed XP boost from {role.mention}.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @level_roles.command(name="add", description="Assign a role as a reward for reaching a leveling level")
    @app_commands.describe(role="The role to give", level="The level at which this role is given")
    @app_permission(command_name="leveling_management")
    @app_commands.guild_only()
    async def level_roles_add(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        level: int
    ):
        if level < 1:
            await interaction.response.send_message(
                "Level must be a positive integer.",
                ephemeral=True
            )
            return

        assert interaction.guild is not None

        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                f"I can't assign {role.mention}. It's higher or equal to my top role.",
                ephemeral=True
            )
            return

        if role.is_default() or role.managed:
            await interaction.response.send_message(
                "That role can't be used as a leveling reward (it's either @everyone or managed by an integration/bot).",
                ephemeral=True
            )
            return

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        
        await bot_db.leveling_db.set_leveling_role(
            guild_id=interaction.guild.id,
            role_id=[role.id],
            level=level
        )

        await interaction.response.send_message(
            f"Alright, {role.mention} will now be given at level **{level}**.",
            allowed_mentions=discord.AllowedMentions.none()
        )


    @level_roles.command( name="remove", description="Remove a role from the leveling rewards")
    @app_commands.describe(role="The role to remove")
    @app_permission(command_name="leveling_management")
    async def level_roles_remove(
        self,
        interaction: discord.Interaction,
        role: discord.Role
    ):
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        assert interaction.guild is not None

        removed = await bot_db.leveling_db.remove_leveling_role(
            guild_id=interaction.guild.id,
            role_id=role.id
        )

        if not removed:
            await interaction.response.send_message(
                f"{role.mention} isn't currently configured as a leveling role.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none()
            )
            return

        await interaction.response.send_message(
            f"{role.mention} has been removed from leveling rewards.",
            allowed_mentions=discord.AllowedMentions.none()
        )

    @app_commands.guild_only()
    @level_roles.command(name="list",description="List all configured leveling role rewards")
    async def list_level_roles(self, interaction: discord.Interaction):
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        assert interaction.guild is not None
        rows = await bot_db.leveling_db.get_all_leveling_roles(
            guild_id=interaction.guild.id
        )

        if not rows:
            await interaction.response.send_message(
                "No leveling roles are configured for this server.",
                ephemeral=True
            )
            return

        lines = []
        for role_id, level in rows:
            role = interaction.guild.get_role(role_id)
            role_display = role.mention if role else f"`Unknown role ({role_id})`"
            lines.append(f"**Level {level}** -> {role_display}")

        embed = discord.Embed(
            title="Leveling Roles",
            description="\n".join(lines),
            color=16777215
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        if isinstance(message.author, discord.User):
            return

        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        try:
            allowed_channels = bot_db.get_channels(message.guild.id, "valid_channel")
            if message.channel.id not in allowed_channels:
                return

            member_role_ids = {role.id for role in message.author.roles}
            boosted_roles = await bot_db.fetch_boosted_roles(message.guild.id)  # We will cache this in memory in future

            result = await bot_db.update_message(
                staff_id=message.author.id,
                guild_id=message.guild.id,
                member_role_ids=member_role_ids,
                boosted_roles=boosted_roles,
                avatar_url=message.author.display_avatar.url,
                name=message.author.name,
            )

            if not (result and result["leveled_up"]):
                return

            new_level = result["new_level"]
            logger.info(
                f"[OnMessage] User {message.author.id} leveled up to {new_level} "
                f"in guild {message.guild.id}"
            )

            role_ids = await bot_db.leveling_db.get_roles_based_on_level(
                message.guild.id,
                new_level
            )

            roles_to_add = []
            for role_id in role_ids:
                role = message.guild.get_role(role_id)

                if role is None:
                    logger.warning(
                        f"[OnMessage] Role {role_id} not found in guild {message.guild.id} "
                        f"(level {new_level} reward)"
                    )
                    continue

                if role in message.author.roles:
                    continue

                if role >= message.guild.me.top_role:
                    logger.warning(
                        f"[OnMessage] Cannot assign role {role.id} ({role.name}) to user "
                        f"{message.author.id}: role is above bot's top role in guild {message.guild.id}"
                    )
                    continue

                roles_to_add.append(role)

            if roles_to_add:
                try:
                    await message.author.add_roles(
                        *roles_to_add,
                        reason=f"Reached leveling level {new_level}"
                    )
                    logger.info(
                        f"[OnMessage] Assigned roles {[r.id for r in roles_to_add]} to "
                        f"user {message.author.id} in guild {message.guild.id}"
                    )
                except discord.Forbidden:
                    logger.warning(
                        f"[OnMessage] Missing permissions to assign roles "
                        f"{[r.id for r in roles_to_add]} to user {message.author.id} "
                        f"in guild {message.guild.id}"
                    )
                except discord.HTTPException:
                    logger.exception(
                        f"[OnMessage] HTTP error assigning roles "
                        f"{[r.id for r in roles_to_add]} to user {message.author.id} "
                        f"in guild {message.guild.id}"
                    )

            return

            await message.channel.send(
                f"🎉 {message.author.mention} leveled up to **level {new_level}**!"
            )

        except Exception:
            logger.exception(
                f"[OnMessage] Failed to update message stats for staff_id={message.author.id} "
                f"in guild_id={message.guild.id}"
            )

async def setup(bot):
    cog = LilyLeveling(bot)
    await bot.add_cog(cog)