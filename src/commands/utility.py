import re
import json
import discord
import aiohttp
import asyncio
import time
import logging


from io import BytesIO
from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.utils.lily_utility import *
from src.core.features.permissions.lily_permissions import app_permission, permission, registered_permissions
from src.core.utils.components.sLIlyGlobalComponents import CommandInfo as CI
from src.core.utils.embeds.sLilyEmbed import ParseAdvancedEmbed
from src.core.utils.types.types import ChannelEnum, NotifiersEnum
from src.core.logging.lily_logging import LilyLoggingController
from zoneinfo import available_timezones, ZoneInfo, ZoneInfoNotFoundError
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.utils.components.sLIlyGlobalComponents import RoleCustomizationModal, Avatar, LeaderboardView
from src.core.visuals.cards.quote import make_quote_card
from src.core.visuals.cards.leaderboard import leaderboard_img
from src.core.features.ticketing.transcript import transcript
from discord.ext import commands
from discord import app_commands

logger = logging.getLogger("lily")


class LilyUtility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.automod_cache = {}

        self.ctx_menu = app_commands.ContextMenu(
            name="Quote",
            callback=self.quote,
        )

        self.bot.tree.add_command(self.ctx_menu)

    async def quote_generator(self, message: discord.Message):

        assert message.guild is not None
        assert isinstance(message.author, discord.Member)

        """ This only works for peoples with staff roles.  Nothing else, so we need to make sure staffs won't abuse this """
        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        allowed_roles = bot_db.get_permission_roles(message.guild.id, "mute")

        author_role_ids = {role.id for role in message.author.roles}

        if not any(role_id in author_role_ids for role_id in allowed_roles):
            return
            
        if message.content.startswith(f"<@{self.bot.user.id}>") or message.content.startswith(f"<@!{self.bot.user.id}>"):
            if message.reference is None:
                return
            content = message.content.lower()
            if "quote" not in content:
                return
            
            message_ref_id = message.reference.message_id

            if message_ref_id is None:
                return
            
            replied_msg = await message.channel.fetch_message(message_ref_id)
            author: discord.Member | discord.User = replied_msg.author
            content = replied_msg.content

            """ Delete the original message if possible """
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            avatar_bytes = await author.display_avatar.read()
            
            image = await asyncio.to_thread(
                make_quote_card,
                image=avatar_bytes,
                quote=content,
                author=author.display_name,
                handle=f"@{author.name}"
            )

            buffer = BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)

            await message.channel.send(file=discord.File(buffer, filename="quote.png"))

    async def afk_evaluator(self, message: discord.Message):
        if message.author.bot:
            return

        if message.guild is None:
            return

        bot_db: BotGlobalsDatabaseAccess = self.bot.db

        afk_entries = await bot_db.get_afk_entries(message.guild.id)

        if message.author.id in afk_entries:
            cleared_row = await bot_db.afk_clear(message.author.id, message.guild.id)

            if cleared_row is not None:
                assert isinstance(message.author, discord.Member)

                try:
                    await message.author.edit(nick=cleared_row["display_name"])
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass

                afk_since = datetime.fromisoformat(cleared_row["timestamp"])
                unix_ts = int(afk_since.timestamp())

                await message.reply(
                    embed=simple_embed(f"Welcome back, {message.author.mention}! I've removed your AFK status. You were AFK Since <t:{unix_ts}:R>", 'check')
                )

        afk_mentions = []

        for user in message.mentions:
            if user.bot:
                continue

            if user.id in afk_entries and user.id != message.author.id:
                row = afk_entries[user.id]
                afk_since = datetime.fromisoformat(row["timestamp"])
                unix_ts = int(afk_since.timestamp())

                afk_mentions.append(
                    f"{user.mention} is AFK: {row['reason']} <t:{unix_ts}:R>"
                )

        if afk_mentions:
            await message.reply("\n".join(afk_mentions), allowed_mentions=discord.AllowedMentions.none())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        if message.guild is None:
            return

        if not isinstance(message.author, discord.Member):
            return

        await self.quote_generator(message)
        await self.afk_evaluator(message)
    
    async def command_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        current = current.lower()

        return [
            app_commands.Choice(name=command.replace("_", " ").title(), value=command)
            for command in registered_permissions
            if current in command.lower()
        ][:25]

    set = app_commands.Group(
        name="set",
        description="Utility setter commands"
    )

    configure = app_commands.Group(
        name="configure",
        description="Utility configuration commands"
    )

    customize = app_commands.Group(
        name="customize",
        description="Utility customization commands"
    )

    remove = app_commands.Group(
        name="remove",
        description="Utility removal commands"
    )

    afk = app_commands.Group(
        name = "afk",
        description="Afk Utilities"
    )

    @commands.hybrid_group(name="timezone", description="Timezone utility commands", aliases=["tz"])
    async def timezone(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply(embed=simple_embed("Please specify a timezone subcommand.", 'cross'), ephemeral=True)

    #UID UTILITY
    @commands.command(name="id")
    async def id(self, ctx: commands.Context, user: discord.Member | None = None):
        if user is None:
            await ctx.reply(str(ctx.author.id))
        else:
            await ctx.reply(str(user.id))
        
    @commands.hybrid_command(name='purge', description="Purge messages with a specified amount")
    @commands.cooldown(1, 10.0, commands.BucketType.user)
    @permission(command_name="purge")
    async def purge(
        self,
        ctx: commands.Context,
        amount: int = 0,
        member: discord.Member | None = None,
        oldest_first: bool = False,
    ):
        if amount <= 0:
            return await ctx.reply(embed=simple_embed("Specify a valid amount", 'cross'), ephemeral=True)

        if amount > 1000:
            return await ctx.reply(embed=simple_embed("You cannot purge more than 1000 messages!", 'cross'), ephemeral=True)

        def check(msg):
            return True if member is None else msg.author == member

        await ctx.defer()
        try:
            if not isinstance(ctx.channel, discord.TextChannel):
                return await ctx.reply(embed=simple_embed("Failed to purge", 'cross'))

            deleted = await ctx.channel.purge(
                limit=amount,
                check=check,
                bulk=True,
                oldest_first=oldest_first,
                reason=f"Purged by {ctx.author.mention}"
            )
            await ctx.reply(embed=simple_embed(f"Deleted {len(deleted)} message(s)."))
        except discord.Forbidden:
            await ctx.reply(embed=simple_embed("I do not have permission to delete messages.", 'cross'))
        except discord.HTTPException:
            await ctx.reply(embed=simple_embed("An unknown error occurred", 'cross'))

            
    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: commands.Context):
        ws_latency = round(self.bot.latency * 1000, 2)

        start = time.perf_counter()
        msg = await ctx.reply("Evaluating...")
        roundtrip = round((time.perf_counter() - start) * 1000, 2)

        await msg.edit(
            content=(
                f"WebSocket Latency: `{ws_latency}ms`\n"
                f"Roundtrip: `{roundtrip}ms`"
            )
        )

    @commands.hybrid_command(name='role', description="Assigns/Removes a specified role from the user (not case-sensitive)")
    @commands.cooldown(rate=5, per=1, type = commands.BucketType.user)
    @permission(command_name="role")
    async def role(
        self,
        ctx: commands.Context,
        user: discord.Member | None = None,
        role: discord.Role | None = None
    ):
        if ctx.guild is None:
            return await ctx.reply(
                embed=simple_embed("You can only use this command inside a guild"),
                ephemeral=True
            )

        author = ctx.author
        assert isinstance(author, discord.Member)

        if user is None or role is None:
            return await ctx.reply(
                view=CI(ctx, "Role", [
                    "role user role",
                    f"role {ctx.guild.me.mention} Moderator",
                    f"role {ctx.guild.me.mention} 1324893524184793130"
                ])
            )

        if (
            author != ctx.guild.owner
            and author != user
            and author.top_role <= user.top_role
        ):
            return await ctx.reply(
                embed=simple_embed("You cannot modify someone with equal or higher top role.", 'cross'),
                ephemeral=True
            )

        if role > author.top_role and author != ctx.guild.owner:
            return await ctx.reply(
                embed=simple_embed("You cannot assign a role that is higher than your top role.", 'cross'),
                ephemeral=True
            )

        if ctx.guild.me.top_role <= role:
            return await ctx.reply(
                embed=simple_embed("I cannot manage that role because it is above my top role.", 'cross'),
                ephemeral=True
            )

        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        author_role_ids = [r.id for r in author.roles]
        allowed = bot_db.can_assign_role(ctx.guild.id, author_role_ids, role.id)

        if not allowed:
            return await ctx.reply(
                embed=simple_embed("You are not allowed to assign this role.", 'cross'),
                ephemeral=True
            )

        if role in user.roles:
            await user.remove_roles(role, reason=f"Role removed by {author}")
            return await ctx.reply(
                embed=simple_embed(f"Removed role **{role.name}** from **{user.name}**."),
                ephemeral=True
            )
        else:
            await user.add_roles(role, reason=f"Role given by {author}")
            return await ctx.reply(
                embed=simple_embed(f"Added role **{role.name}** to **{user.name}**."),
                ephemeral=True
            )

    @customize.command(name="role", description="Customize your role")  
    @app_commands.checks.cooldown(1, 5.0)
    async def customize_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        name: str | None = None,
        primary_color: str | None = None,
        secondary_color: str | None = None,
        icon: discord.Attachment | None = None
    ):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("You need to use this command inside a guild"), ephemeral=True)

        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(embed=simple_embed("I can't edit a role that is above me", 'cross'), ephemeral=True)

        assert isinstance(interaction.user, discord.Member)

        await interaction.response.defer()

        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        valid_roles = await bot_db.get_role_mapping(interaction.user.id, interaction.guild.id)

        if role.id not in valid_roles:
            return await interaction.followup.send(embed=simple_embed("You don't have any roles mapped that you can customize", 'cross'), ephemeral=True)

        def parse_hex_color(hex_str: str) -> discord.Color:
            hex_str = hex_str.strip().lstrip('#')
            if len(hex_str) != 6:
                raise ValueError(f"Invalid hex color: '{hex_str}'")
            return discord.Color(int(hex_str, 16))

        parameters = {}

        if name is not None:
            parameters["name"] = name

        if icon is not None:
            parameters["display_icon"] = await icon.read()

        if primary_color is not None:
            try:
                parameters["color"] = parse_hex_color(primary_color)
            except ValueError:
                return await interaction.followup.send(embed=simple_embed("Invalid color format.", 'cross'), ephemeral=True)

        if secondary_color is not None:
            try:
                parameters["secondary_color"] = parse_hex_color(secondary_color)
            except ValueError:
                return await interaction.followup.send(embed=simple_embed("Invalid color format.", 'cross'), ephemeral=True)

        try:
            await role.edit(**parameters, reason=f"Role customized by {interaction.user}")
            await interaction.followup.send(embed=simple_embed("Successfully updated role!"), ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(embed=simple_embed("I don't have app_permission to edit roles", 'cross'), ephemeral=True)
        except ValueError as e:
            await interaction.followup.send(embed=simple_embed(f"Invalid parameter value: {e}", 'cross'), ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(embed=simple_embed(f"An Unknown error occured while editing a role", 'cross'), ephemeral=True)

    @app_permission(command_name="set_rolecustomize")
    @set.command(name="rolecustomize", description="Allows a person to customize a role without manage roles")
    async def set_role_customize(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("You need to use this command inside an guild"))

        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        await bot_db.add_role_mapping(
            member.id,
            interaction.guild.id,
            role.id
        )
        
        await interaction.response.send_message(embed=simple_embed(f"Successfully added customizable entry for {member.mention} with {role.mention}"), ephemeral=True)
        await member.send(f"Hey, You can now customize {role.name} (dev_id: {role.id}) in {interaction.guild.name}.  Use `/customize role` to see what happens!")

    @app_permission(command_name="remove_rolecustomize")
    @remove.command(name="rolecustomize", description="Removes a person from customizing a role without manage roles")
    async def remove_role_customize(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("You need to use this command inside an guild"))
        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        await bot_db.remove_role_mapping(
            member.id,
            interaction.guild.id,
            role.id
        )

        await interaction.response.send_message(embed=simple_embed(f"Successfully removed customizable entry for {role.mention} assigned to {member.mention}"), ephemeral=True)
        await member.send(f"Hey, You can no longer customize {role.name} (dev_id: {role.id}) in {interaction.guild.name}.")

    @customize.command(name='bot', description='Customize the bot for this server (visually)')
    @app_commands.checks.cooldown(1, 5.0)
    @app_permission(command_name="edit_profile", restrict=True)
    async def edit_profile(self, interaction: discord.Interaction, bio: str, avatar: discord.Attachment, banner: discord.Attachment):
        await interaction.response.defer()
        try:
            guild = interaction.guild
            assert guild is not None
            bot_member = guild.me
            avatar_bytes = await avatar.read()
            banner_bytes = await banner.read()
            await bot_member.edit(avatar=avatar_bytes,banner=banner_bytes,bio=bio)

            await interaction.followup.send(embed=simple_embed("Profile Edit Success. Will be updated within few mins."))
        except Exception as e:
            print(f"Exception [edit_profile] {e}")
            await interaction.followup.send(embed=simple_embed("An Unknown error Occured"))

    @app_commands.command(name="about", description="Know something about the bot")
    @app_commands.checks.cooldown(1, 5.0)
    async def about(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="About Me!",
            description="## Name : Lily\n- No Idea about this name to be honest.",
            color=0xFFFFFF
        )

        embed.add_field(
            name="Developers",
            value="- Shree (Lead)\n- Texio\n- Lily.cs",
            inline=False
        )

        embed.add_field(
            name="Code Maintainer",
            value="- Senior Shree.",
            inline=False
        )

        embed.add_field(
            name="Profile and Banner Information",
            value=(
                "- [Avatar (Modified)](https://x.com/marmalade_icons/status/1116802730536906755?s=20)\n"
                "- Character Source : Kaede Akamatsu (Danganronpa V3: Killing Harmony)\n"
                "- Banner Source : Custom Fan art"
            ),
            inline=False
        )

        embed.add_field(
            name="Licensing Terms",
            value="- Open Source Free to Modify/Redistribute Licensing. (Incl. Credits)",
            inline=False
        )

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        await interaction.response.send_message(embed=embed)
    
    @app_permission(command_name="set_channel")
    @set.command(name="channel", description="Creates an embed based on JSON config and sends it to a specific channel")
    async def assign_channel(self, interaction: discord.Interaction, type: ChannelEnum, channel: discord.TextChannel):
        if interaction.guild is None:
            await interaction.response.send_message(embed=simple_embed("This command can only be used inside an guild", 'cross'))
            return

        db: BotGlobalsDatabaseAccess = self.bot.db
        await db.set_channel(interaction.guild.id, channel.id, type.value)

        await interaction.response.send_message(embed=simple_embed(f"Successfully assigned `{type.value.title()}` for {channel.mention}"))

    @set.command(name="notifiers", description="Creates a notifier (webhook) when an value updates")
    @app_commands.checks.cooldown(1, 20.0)
    @app_permission(command_name="set_notifiers")
    async def set_notifiers(self, interaction: discord.Interaction, type: NotifiersEnum, channel: discord.TextChannel, webhook_url: str):
        if interaction.guild is None:
            await interaction.response.send_message(embed=simple_embed("This command can only be used inside an guild", 'cross'))
            return
        
        db: BotGlobalsDatabaseAccess = self.bot.db
        if channel is not None:
            await interaction.response.defer()
            webhook = await channel.create_webhook(name="Lily Listeners")
            webhook_url = webhook.url
            await db.set_webhook(interaction.guild.id, type.value, webhook_url)
            await interaction.followup.send(embed=simple_embed(f"Successfully created a webhook to listen `{type.value}`"))
        else:
            await db.set_webhook(interaction.guild.id, type.value, webhook_url)
            await interaction.response.send_message(embed=simple_embed(f"Successfully assigned a webhook to listen `{type.value}`"))

    @app_commands.guild_only()
    @app_permission(command_name="set_permission")
    @set.command(
        name="app_permission",
        description="Allocates app_permission to a role for a command"
    )
    @app_commands.autocomplete(command=command_autocomplete)
    async def set_permission(
        self,
        interaction: discord.Interaction,
        command: str,
        role: discord.Role,
    ):
        assert interaction.guild is not None

        db: BotGlobalsDatabaseAccess = self.bot.db
        await db.set_permission(
            interaction.guild.id,
            role.id,
            command,
        )

        formatted = command.replace("_", " ").title()

        await interaction.response.send_message(
            embed=simple_embed(
                f"Successfully assigned `{formatted}` app_permission to {role.mention}"
            )
        )

    @app_commands.guild_only()
    @app_permission(command_name="remove_permission")
    @remove.command(
        name="app_permission",
        description="Removes a command app_permission from a role"
    )
    @app_commands.autocomplete(command=command_autocomplete)
    async def remove_permission(
        self,
        interaction: discord.Interaction,
        command: str,
        role: discord.Role,
    ):
        assert interaction.guild is not None

        db: BotGlobalsDatabaseAccess = self.bot.db

        await db.remove_permission(
            interaction.guild.id,
            role.id,
            command,
        )

        formatted = command.replace("_", " ").title()

        await interaction.response.send_message(
            embed=simple_embed(
                f"Successfully removed `{formatted}` app_permission from {role.mention}"
            )
        )
        
    @app_permission(command_name="permissions")
    @app_commands.command(name="permissions", description="List out permissions that a role has")
    async def permissions(self, interaction: discord.Interaction, role: discord.Role):
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=simple_embed(
                    "This command can only be used inside a guild",
                    "cross"
                )
            )
            return

        db: BotGlobalsDatabaseAccess = self.bot.db
        permissions = db.get_permissions(interaction.guild.id, role.id)

        if not permissions:
            await interaction.response.send_message(
                embed=simple_embed(
                    f"{role.mention} has no configured permissions.",
                    "cross"
                )
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(title="Permissions", description=", ".join(permissions), color=16777215)
        )

    @app_permission(command_name="set_prefix")
    @set.command(name="prefix", description="Change prefix of the bot")
    async def set_prefix(self, interaction: discord.Interaction, prefix: str):
        if interaction.guild is None:
            await interaction.response.send_message(embed=simple_embed("This command can only be used inside an guild", 'cross'))
            return
        
        db: BotGlobalsDatabaseAccess = self.bot.db
        await db.set_prefix(interaction.guild.id, prefix)

        await interaction.response.send_message(embed=simple_embed(f"Successfully assigned **{prefix}** as prefix"))

    @app_permission(command_name="configure_role")
    @configure.command(name="role", description="Configure some attributes of the role")
    @app_commands.guild_only()
    async def configure_role(self, interaction: discord.Interaction, role: discord.Role):
        assert interaction.guild is not None
        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        role_config = await bot_db.get_role_configuration(interaction.guild.id, role.id)
        await interaction.response.send_modal(RoleCustomizationModal(role.id, self.bot.db, role.name, role_config))

    @app_commands.command(name="nick", description="Set a nickname for a member")
    @app_permission(command_name="nick")
    async def set_nickname(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        name: str
    ):
        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)
        assert isinstance(interaction.guild.me, discord.Member)

        error = await change_nickname(
            interaction.user,
            interaction.guild.me,
            member,
            name
        )

        if error:
            return await interaction.response.send_message(
                embed=simple_embed(error, "cross")
            )

        await interaction.response.send_message(
            embed=simple_embed(
                f"Successfully changed {member.mention}'s nickname to **{name}**."
            )
        )

    @permission(command_name="nick")
    @commands.command(name="nick", aliases=["nickname"])
    async def nick(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        name: str
    ):
        assert ctx.guild is not None
        assert isinstance(ctx.author, discord.Member)
        assert isinstance(ctx.guild.me, discord.Member)

        error = await change_nickname(
            ctx.author,
            ctx.guild.me,
            member,
            name
        )

        if error:
            return await ctx.reply(
                embed=simple_embed(error, "cross")
            )

        await ctx.reply(
            embed=simple_embed(
                f"Successfully changed {member.mention}'s nickname to **{name}**."
            )
        )

    async def quote(self, interaction: discord.Interaction, message: discord.Message) -> None:
        await interaction.response.defer()
        avatar_bytes = await message.author.display_avatar.read()
            
        image = await asyncio.to_thread(
            make_quote_card,
            image=avatar_bytes,
            quote=message.content,
            author=message.author.display_name,
            handle=f"@{message.author.name}"
        )

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        await interaction.followup.send(file=discord.File(buffer, filename="quote.png"))

    @app_commands.command(name="privacy_policy", description="Get a link to the bot's Privacy Policy")
    @app_commands.checks.cooldown(1, 5.0)
    async def privacy_policy(self, interaction: discord.Interaction):
        embed = discord.Embed(
            color=16777215,
            title="Lily Privacy Policy Notice",
            description="## __Introduction__\n- This Privacy Policy covers what data Lily collects and how it is handled. Lily only collects what is necessary to function — including Discord account identifiers, server configuration, moderation logs, and feature-specific data such as staff records, message activity counts, and ticket references. Message content is never stored, and transcript data remains within your own server. Your data is never sold or shared with third parties, and is retained only for as long as it is needed. Server owners and users have full rights to access, correct, or delete their data at any time, and any meaningful changes to this policy will be communicated in advance.\n### [VIEW OUR PRIVACY POLICY](https://ittzspsv.github.io/LilyV2/privacy)",
        )
        embed.set_footer(
                text="By using Lily, you acknowledge and agree to the data collection and usage practices described in this Privacy Policy.",
            )
        
        if interaction.guild is not None and interaction.guild.me is not None:
            embed.set_thumbnail(url=interaction.guild.me.display_avatar.url)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @permission(command_name="sync", restrict=True)
    @commands.command(name="sync")
    async def sync(self, ctx: commands.Context):
        if ctx.guild is None:
            return await ctx.send("This command can only be executed inside an guild")

        guild = discord.Object(id=ctx.guild.id)

        self.bot.tree.copy_global_to(guild=guild)

        synced = await self.bot.tree.sync(guild=guild)

        await ctx.send(
            f"Synced {len(synced)} commands to {ctx.guild.name}"
        )

    @app_commands.command(name='avatar', description='Get avatar of yourself or other member')
    async def avatar(self, interaction: discord.Interaction, member: discord.Member | None = None):
        await interaction.response.send_message(view=Avatar(member or interaction.user))

    @commands.command(name="avatar", aliases=["av"])
    async def _avatar(self, ctx: commands.Context, member: discord.Member | None):
        await ctx.reply(view=Avatar(member or ctx.author))

    @app_commands.command(name="evaluate", description="Evaluates an expression in any form")
    @app_permission(command_name="evaluate")
    async def message(
        self,
        interaction: discord.Interaction,
        message: str,
        snowflake: str | None = None
    ):
        channel = interaction.channel

        if not isinstance(channel, (discord.Thread, discord.TextChannel)):
            await interaction.response.send_message(
                "Cannot send messages here.",
                ephemeral=True
            )
            return

        message = message.replace("@everyone", "").replace("@here", "").strip()

        if snowflake is not None:
            try:
                msg = await channel.fetch_message(int(snowflake))
                msg = await msg.reply(content=message)
            except discord.NotFound:
                await interaction.response.send_message(
                    "Message not found.",
                    ephemeral=True
                )
                return
        else:
            msg = await channel.send(content=message, allowed_mentions=discord.AllowedMentions(roles=False, everyone=False))


        print(f"Message Sent By {interaction.user.id} reference {msg.jump_url}")
        with open("bot.log", "a", encoding="utf-8") as f:
            f.write(
                f"Message Sent By {interaction.user.id} reference {msg.jump_url}\n"
            )
        await interaction.response.send_message(
            "Successfully sent!",
            ephemeral=True
        )

    @timezone.command(name="get", description="Get a timezone of a user")
    async def get_timezone(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None
    ):
        db: BotGlobalsDatabaseAccess = self.bot.db

        if ctx.guild is None:
            return await ctx.reply(
                embed=simple_embed("This command can only be used inside a guild", 'cross'),
                ephemeral=True
            )

        target_member = member or await ctx.guild.fetch_member(ctx.author.id)

        tz_name = await db.get_timezone(target_member.id, ctx.guild.id)

        if not tz_name:
            return await ctx.reply(
                embed=simple_embed(f"**{target_member.display_name}** hasn't set their timezone yet.", 'cross'),
                ephemeral=True
            )

        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            return await ctx.reply(
                embed=simple_embed("Invalid timezone configured", 'cross'),
                ephemeral=True
            )

        now = datetime.now(tz)

        formatted_date = now.strftime("%A, %B %-d, %Y")
        formatted_time = now.strftime("%-I:%M %p")

        description = (
            f"### {target_member.display_name}'s Timezone\n"
            f"**Timezone:** `{tz_name}`\n"
            f"**Local time:** {formatted_time}\n"
            f"**Date:** {formatted_date}"
        )

        requester_tz_name = await db.get_timezone(ctx.author.id, ctx.guild.id)

        if requester_tz_name:
            try:
                requester_tz = ZoneInfo(requester_tz_name)
            except ZoneInfoNotFoundError:
                requester_tz = None

            if requester_tz is not None:
                requester_now = datetime.now(requester_tz)
                target_offset = now.utcoffset()
                requester_offset = requester_now.utcoffset()

                if target_offset is not None and requester_offset is not None:
                    difference_hours = (target_offset - requester_offset).total_seconds() / 3600

                    if difference_hours == 0:
                        difference_text = "You are in the **same timezone**."
                    elif difference_hours > 0:
                        difference_text = f"They are **{difference_hours:g} hours ahead** of you."
                    else:
                        difference_text = f"They are **{abs(difference_hours):g} hours behind** you."

                    description += f"\n\n**Compared to you:**\n{difference_text}"

        embed = discord.Embed(description=description, color=16777215)
        embed.set_thumbnail(url=target_member.display_avatar.url)

        await ctx.reply(embed=embed)

    async def timezone_autocomplete(self, interaction: discord.Interaction, current):
            matches = [
                tz for tz in sorted(available_timezones())
                if current.lower() in tz.lower()
            ]
            return [
                app_commands.Choice(name=tz, value=tz)
                for tz in matches[:25]
            ]

    @timezone.command(name="set", description="Assign your own timezone")
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    async def set_timezone(
        self,
        ctx: commands.Context,
        timezone: str
    ):
        db: BotGlobalsDatabaseAccess = self.bot.db

        if ctx.guild is None:
            return await ctx.reply(
                embed=simple_embed("This command can only be used inside a guild", 'cross'),
                ephemeral=True
            )

        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            return await ctx.reply(
                embed=simple_embed(f"`{timezone}` is not a valid timezone.", 'cross'),
                ephemeral=True
            )

        await db.set_timezone(
            ctx.author.id,
            ctx.guild.id,
            timezone
        )

        now = datetime.now(ZoneInfo(timezone))

        await ctx.reply(
            embed=simple_embed(
                f"Your timezone has been set to `{timezone}`.\n"
                f"Your local time is **{now.strftime('%A, %-I:%M %p')}**.", bold=False
            ),
            ephemeral=True
        )


    @commands.hybrid_command(
        name="myprefix",
        description="Get your bot prefix assigned to this server"
    )
    async def get_my_prefix(
        self,
        ctx: commands.Context,
        prefix: str | None = None
    ):
        if ctx.guild is None:
            await ctx.reply(
                embed=simple_embed(
                    "You can only use this command inside a guild!"
                )
            )
            return

        bot_db: BotGlobalsDatabaseAccess = self.bot.db

        if prefix is None:
            prefix = bot_db.get_prefix_member(
                ctx.author.id,
                ctx.guild.id
            )

            if prefix:
                await ctx.reply(f"Your prefix is `{prefix}`")
            else:
                await ctx.reply(
                    f"You haven't configured your prefix yet. "
                    f"Hence the default prefix for this server is "
                    f"`{bot_db.get_prefix(ctx.guild.id)}`"
                )
        else:
            stored_prefix = prefix if len(prefix) == 1 else prefix + " "

            await bot_db.set_prefix_member(
                ctx.author.id,
                ctx.guild.id,
                stored_prefix
            )

            await ctx.reply(
                embed=simple_embed(
                    f"Successfully assigned prefix `{prefix}` for you!"
                )
            )

    @permission(command_name="afk_set")
    @commands.command(name="afk", description="Set an afk status")
    async def setafk(self, ctx: commands.Context, *, reason: str):
        try:
            bot_db: BotGlobalsDatabaseAccess = self.bot.db

            if ctx.guild is None:
                await ctx.reply(embed=simple_embed("This command can only be used inside a guild", 'cross'))
                return

            assert isinstance(ctx.author, discord.Member)

            await bot_db.afk_set(
                ctx.author.id,
                ctx.guild.id,
                reason,
                ctx.author.display_name
            )

            if not ctx.author.display_name.startswith("[AFK] "):
                new_nick = f"[AFK] {ctx.author.display_name}"

                if len(new_nick) > 32:
                    new_nick = new_nick[:32]

                try:
                    await ctx.author.edit(nick=new_nick)
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass

            await ctx.reply(embed=simple_embed(f"You are now AFK: {reason}"))
        except Exception as e:
            print(e)

    @app_permission(command_name = "afk clear")
    @afk.command(name = "clear", description="Clear an AFK for an user")
    async def clear_afk(self, interaction: discord.Interaction, member: discord.Member):
        bot_db: BotGlobalsDatabaseAccess = self.bot.db

        if interaction.guild is None:
            await interaction.response.send_message(embed=simple_embed("This command can only be used inside a guild", 'cross'))
            return

        cleared_row = await bot_db.afk_clear(member.id, interaction.guild.id)

        if cleared_row is None:
            await interaction.response.send_message(
                embed=simple_embed(f"{member.display_name} is not currently AFK", 'cross')
            )
            return

        try:
            await member.edit(nick=cleared_row["display_name"])
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass

        await interaction.response.send_message(
            embed=simple_embed(f"Cleared AFK status for {member.display_name}")
        )

    @app_commands.command(name="profile", description="Display your profile")
    async def profile(self, interaction: discord.Interaction, member: discord.Member | None = None):
        ...

    @commands.hybrid_command(name="messages", description="View the number of messages sent by you or an user")
    async def messages(self, ctx: commands.Context, member: discord.Member | discord.User | None = None):
        db: BotGlobalsDatabaseAccess = self.bot.db

        if ctx.guild is None:
            await ctx.reply(
                ephemeral=True,
                embed=simple_embed("This command can only be executed inside a guild", 'cross')
            )
            return

        target = member if member is not None else ctx.author

        msg_stats = await db.get_messages(ctx.guild.id, target.id)

        view = discord.ui.LayoutView().add_item(
            discord.ui.Container(
                discord.ui.Section(
                    discord.ui.TextDisplay(content=f"## {target.display_name}'s Messages"),
                    discord.ui.TextDisplay(
                        content=(
                            f"> **Today**:  {msg_stats['daily_messages']:,}\n"
                            f"> **This Week**:  {msg_stats['weekly_messages']:,}\n"
                            f"> **This Month**:  {msg_stats['monthly_messages']:,}\n"
                            f"> **Total**:  {msg_stats['total_messages']:,}"
                        )
                    ),
                    accessory=discord.ui.Thumbnail(
                        media=target.display_avatar.url,
                    ),
                ),
                discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            )
        )

        await ctx.reply(view=view)

    @app_commands.command(name="leaderboard", description="View the message leaderboard")
    @app_commands.describe(type="Which leaderboard to view")
    @app_commands.choices(type=[
        app_commands.Choice(name="Daily", value=0),
        app_commands.Choice(name="Weekly", value=1),
        app_commands.Choice(name="Monthly", value=2),
        app_commands.Choice(name="Total", value=3),
    ])
    @app_commands.checks.cooldown(1, 20.0)
    @app_commands.guild_only()
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[int],
    ):
        leaderboard_type = type.value
        db: BotGlobalsDatabaseAccess = self.bot.db
        if interaction.guild is None:
            await interaction.response.send_message(
                ephemeral=True,
                embed=simple_embed("This command can only be executed inside a guild", 'cross')
            )
            return

        await interaction.response.defer()

        try:
            results = await db.leaderboard(
                interaction.guild.id,
                leaderboard_type,
                interaction.user.id,
                page=1,
            )
        except Exception:
            logger.exception(
                "Failed to fetch leaderboard for guild_id=%s type=%s",
                interaction.guild.id,
                leaderboard_type,
            )
            await interaction.followup.send(
                embed=simple_embed("Something went wrong while fetching the leaderboard.", 'cross')
            )
            return

        top_three = results["leaderboard"][:3]

        img_bytes = None
        if len(top_three) == 3:
            try:
                podium_members = []
                for m in top_three:
                    member_id = m["member_id"]
                    _member = interaction.guild.get_member(member_id) or await interaction.guild.fetch_member(member_id)

                    podium_members.append({
                        "display_name": m["name"],
                        "avatar_url": _member.display_avatar.url,
                        "avatar_deco_url": _member.avatar_decoration.url if _member.avatar_decoration else "",
                        "messages": f"{m['messages']:,}",
                    })

                img_bytes = await leaderboard_img(tuple(podium_members))

                if img_bytes is None:
                    logger.warning(
                        "leaderboard_img returned None for guild_id=%s type=%s (avatar/deco fetch likely failed)",
                        interaction.guild.id,
                        leaderboard_type,
                    )
            except discord.NotFound:
                logger.warning(
                    "Top-3 member lookup failed (member left guild?) for guild_id=%s type=%s",
                    interaction.guild.id,
                    leaderboard_type,
                )
            except Exception:
                logger.exception(
                    "Failed to build podium image for guild_id=%s type=%s",
                    interaction.guild.id,
                    leaderboard_type,
                )

        view = LeaderboardView(
            interaction.guild.name,
            results,
            db,
            guild_id=interaction.guild.id,
            leaderboard_type=leaderboard_type,
            requester_id=interaction.user.id,
            leaderboard_img_available=img_bytes is not None
        )

        try:
            if img_bytes is not None:
                file = discord.File(BytesIO(img_bytes), filename="leaderboard.png")
                await interaction.followup.send(view=view, file=file, allowed_mentions=discord.AllowedMentions.none())
            else:
                await interaction.followup.send(view=view, allowed_mentions=discord.AllowedMentions.none())

            view.message = await interaction.original_response()
        except Exception:
            logger.exception(
                "Failed to send leaderboard message for guild_id=%s type=%s",
                interaction.guild.id,
                leaderboard_type,
            )

async def setup(bot):
    await bot.add_cog(LilyUtility(bot))