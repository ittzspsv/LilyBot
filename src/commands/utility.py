import re
import json
import discord
import aiohttp
import asyncio
import time


from io import BytesIO
from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.utils.lily_utility import *
from src.core.features.permissions.lily_permissions import app_permission, permission
from src.core.utils.components.sLIlyGlobalComponents import CommandInfo as CI
from src.core.utils.embeds.sLilyEmbed import ParseAdvancedEmbed
from src.core.utils.types.types import ChannelEnum, CommandEnum, NotifiersEnum
from src.core.logging.lily_logging import LilyLoggingController
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.utils.components.sLIlyGlobalComponents import RoleCustomizationModal, Avatar, AutomodUpdate
from src.core.visuals.cards.quote import make_quote_card
from discord.ext import commands
from discord import app_commands


class LilyUtility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.automod_cache = {}

        self.ctx_menu = app_commands.ContextMenu(
            name="Quote",
            callback=self.quote,
        )

        self.bot.tree.add_command(self.ctx_menu)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        if message.guild is None:
            return

        if not isinstance(message.author, discord.Member):
            return
        
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
    
    async def command_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        current = current.lower()

        return [
            app_commands.Choice(name=command.name, value=command.value)
            for command in CommandEnum
            if current in command.value.lower()
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
        

    # SERVER UTILITY
    @app_commands.command(name='list', description='lists the total number of users in the server')
    @app_permission(command_name="list", restrict=True)
    async def ServerList(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            guilds = self.bot.guilds
            chunk_size = 10

            for i in range(0, len(guilds), chunk_size):
                chunk = guilds[i:i+chunk_size]
                description = ""
                for guild in chunk:
                    description += f"**{guild.name} - {guild.member_count}**\n"
                
                embed = discord.Embed(
                    title=f"Server List (Page {i//chunk_size + 1}/{(len(guilds) + chunk_size - 1)//chunk_size})",
                    description=description,
                    color=discord.Color.blue()
                )
                await interaction.followup.send(embed=embed)
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Exception [SERVER LIST] {e}")

    #UID UTILITY
    @commands.command(name="id")
    async def id(self, ctx: commands.Context, user: discord.Member | None = None):
        if user is None:
            await ctx.reply(str(ctx.author.id))
        else:
            await ctx.reply(str(user.id))
        
    @app_commands.command(name='purge',description='Purge Message with specified amount')
    @app_commands.checks.cooldown(1, 10.0)
    @app_permission(command_name="purge")
    async def purge(self, interaction: discord.Interaction, amount: int=0, member: discord.Member | None = None):

        if amount <= 0:
            await interaction.response.send_message(embed=simple_embed("Specify a valid amount", 'cross'))
        if amount > 1000:
            await interaction.response.send_message(embed=simple_embed("You cannot purge more than 1000 messages!", 'cross'))
            return

        def check(msg):
            return True if member is None else msg.author == member

        await interaction.response.defer()
        try:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.followup.send(embed=simple_embed("Failed to purge", 'cross'))
                return
            deleted = await interaction.channel.purge(limit=amount, check=check, bulk=True)
            await interaction.followup.send(embed=simple_embed(f"Deleted {len(deleted)} message(s)."))
        except discord.Forbidden:
            await interaction.followup.send(embed=simple_embed("I do not have app_permission to delete messages.", 'cross'))
        except discord.HTTPException as e:
            await interaction.followup.send(embed=simple_embed("An Unknown error occured", 'cross'))

    @commands.command(name="ping")
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

    @app_commands.command(name='role',description='Assigns/Removes a specified role from the user (not case-sensitive)')
    @app_commands.checks.cooldown(1, 5.0)
    @app_permission(command_name="role")
    async def role(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        if interaction.guild is None or isinstance(interaction.user, discord.User):
            await interaction.response.send_message(embed=simple_embed("You can only use this command inside an guild"))
            return
        if user is None and role_input is None:
            await interaction.response.send_message(view=CI(interaction, "Role", ["role user role", f"role {interaction.guild.me.mention} Moderator", f"role {interaction.guild.me.mention} 1324893524184793130"]))
            return

        author = interaction.user

        if (
            author != interaction.guild.owner
            and author != user
            and author.top_role <= user.top_role
        ):
            return await interaction.response.send_message(embed=simple_embed("You cannot modify someone with equal or higher top role.", 'cross'))

        if role > author.top_role and author != interaction.guild.owner:
            return await interaction.response.send_message(embed=simple_embed("You cannot assign a role that is higher than your top role.", 'cross'))

        if interaction.guild.me.top_role <= role:
            return await interaction.response.send_message(embed=simple_embed("I cannot manage that role because it is above my top role.", 'cross'))

        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        author_role_ids = [r.id for r in author.roles]
        allowed = bot_db.can_assign_role(interaction.guild.id, author_role_ids, role.id)

        if not allowed:
            return await interaction.response.send_message(embed=simple_embed("You are not allowed to assign this role.", 'cross'))

        if role in user.roles:
            await user.remove_roles(role, reason=f"Role removed by {author}")
            return await interaction.response.send_message(embed=simple_embed(f"Removed role **{role.name}** from **{user.name}**."))
        else:
            await user.add_roles(role, reason=f"Role given by {author}")
            return await interaction.response.send_message(embed=simple_embed(f"Added role **{role.name}** to **{user.name}**."))

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
            return await interaction.response.send_message(embed=simple_embed("You need to use this command inside a guild"))

        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(embed=simple_embed("I can't edit a role that is above me", 'cross'))

        assert isinstance(interaction.user, discord.Member)

        await interaction.response.defer()

        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        valid_roles = await bot_db.get_role_mapping(interaction.user.id, interaction.guild.id)

        if role.id not in valid_roles:
            return await interaction.followup.send(embed=simple_embed("You don't have any roles mapped that you can customize", 'cross'))

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
                return await interaction.followup.send(embed=simple_embed("Invalid color format.", 'cross'))

        if secondary_color is not None:
            try:
                parameters["secondary_color"] = parse_hex_color(secondary_color)
            except ValueError:
                return await interaction.followup.send(embed=simple_embed("Invalid color format.", 'cross'))

        try:
            await role.edit(**parameters, reason=f"Role customized by {interaction.user}")
            await interaction.followup.send("Successfully updated role!")
        except discord.Forbidden:
            await interaction.followup.send(embed=simple_embed("I don't have app_permission to edit roles", 'cross'))
        except ValueError as e:
            await interaction.followup.send(embed=simple_embed(f"Invalid parameter value: {e}", 'cross'))
        except discord.HTTPException as e:
            await interaction.followup.send(embed=simple_embed(f"An Unknown error occured while editing a role", 'cross'))

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
        
        await interaction.response.send_message(embed=simple_embed(f"Successfully added customizable entry for {member.mention} with {role.mention}"))
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

        await interaction.response.send_message(embed=simple_embed(f"Successfully removed customizable entry for {role.mention} assigned to {member.mention}"))
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
    
    @app_commands.command(name="embed_create", description="Creates an embed based on JSON config and sends it to a specific channel")
    @app_commands.checks.cooldown(1, 80.0)
    @app_permission(command_name="create_embed", restrict=True)
    async def create_embed(self, interaction: discord.Interaction, channel_to_send: discord.TextChannel, * ,embed_json_config: str = "{}"):
        if interaction.guild is None:
            await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))
            return

        await interaction.response.defer()
        try:
            if embed_json_config.startswith("http://") or embed_json_config.startswith("https://"):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(embed_json_config) as resp:
                            if resp.status != 200:
                                await interaction.followup.send("Failed to fetch data from the provided link.")
                                return
                            embed_json_config = await resp.text()
                except Exception as fetch_error:
                    await interaction.followup.send(f"Fetch Failure {str(fetch_error)}")
                    return

            
            try:
                json_data = json.loads(embed_json_config)
            except json.JSONDecodeError:
                await interaction.followup.send("Invalid JSON Format")
                return
            
            try:
                logs_controller: LilyLoggingController = self.bot.logging_controller
                content, embeds = ParseAdvancedEmbed(json_data)
                await channel_to_send.send(content=content, embeds=embeds)
                await interaction.followup.send(embed=simple_embed("Embed sent successfully."))
                await logs_controller.write_log(interaction, interaction.user.id, f"Has Sent an Embed to <#{channel_to_send.id}>")
            except Exception as embed_error:
                await interaction.followup.send(f"Parser Failure: {str(embed_error)}")

        except Exception as e:
            await interaction.followup.send(f"Unhandled Exception: {str(e)}")

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
        
        await interaction.response.send_message(embed=embed)
        
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
    @app_permission(command_name="evaluate", restrict=True)
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

        if snowflake is not None:
            try:
                msg = await channel.fetch_message(int(snowflake))
                await msg.reply(content=message)
            except discord.NotFound:
                await interaction.response.send_message(
                    "Message not found.",
                    ephemeral=True
                )
                return
        else:
            await channel.send(content=message)

        await interaction.response.send_message(
            "Successfully sent!",
            ephemeral=True
        )


    @set.command(name="automod", description="Updates an automod (add / remove new entries)")
    @app_permission(command_name="set_automod")
    @app_commands.guild_only()
    async def set_automod(
        self,
        interaction: discord.Interaction,
    ) -> None:

        assert interaction.guild is not None
        
        rules = await interaction.guild.fetch_automod_rules()
        
        
        view = AutomodUpdate(rules)
        await interaction.response.send_message(view=view, ephemeral=True)




async def setup(bot):
    await bot.add_cog(LilyUtility(bot))