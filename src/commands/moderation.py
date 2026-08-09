import discord, discord.app_commands as app_commands
from discord.ext import commands
from typing import Optional, Any, Dict
import re
from enum import Enum

from src.core.utils.components.sLIlyGlobalComponents import CommandInfo
from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.features.moderation.components.sLilyModerationComponents import AppealForumCustomize
from src.core.features.permissions.lily_permissions import permission, app_permission
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.logging.lily_logging import LilyLoggingController

from src.core.features.moderation.controller.lily_moderation_controller import (
    ban_user,
    quarantine_user,
    mute_user,
    unmute as unmute_fn,
    unban as unban_fn,
    release as release_fn,
    warn as warn_fn,
    case_edit as case_edit_fn,
    case_delete as case_delete_fn,
    ms as ms_fn,
    mod_logs,
    moderation_insights as moderation_insights_fn,
    setup_mod_appeal,
    accept_appeal as accept_appeal_fn,
    reject_appeal as reject_appeal_fn,
)


class ModType(str, Enum):
        All = "all"
        Ban = "ban"
        Warn = "warn"
        Mute = "mute"
        Quarantine = "quarantine"
        Unmute = "unmute"
        QuarantineRelease = "quarantine_release"
        Unban = "unban"

class LilyModeration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cached_members: Dict[int, discord.Member] = {}

    @property
    def bot_db(self) -> BotGlobalsDatabaseAccess:
        return self.bot.db

    @property
    def logging_controller(self) -> LilyLoggingController:
        return self.bot.logging_controller

    def strip_mention(self, content: str, bot_user_id: int) -> str:
        return re.sub(rf"<@!?{bot_user_id}>", "", content).strip()

    async def _reply(self, message: discord.Message, bot: Any) -> bool:
        ref = message.reference
        if ref is None:
            return False

        resolved = ref.resolved
        if isinstance(resolved, discord.Message):
            return resolved.author.id == bot.user.id

        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        bot_db: BotGlobalsDatabaseAccess = self.bot.db

        if message.guild is not None:
            if not isinstance(message.channel, discord.Thread):
                return
            
            is_mention = self.bot.user in message.mentions
            is_reply_to_bot = await self._reply(message, self.bot)

            if not (is_mention or is_reply_to_bot):
                return

            """ Send the message to the users DM """
            appeal = await bot_db.get_appeal_complete(message.channel.id)
            if appeal is None:
                return

            if appeal["moderator_id"] != message.author.id:
                await message.add_reaction("❌")
                return
            
            member: discord.Member | None = self.cached_members.get(appeal["target_user_id"])
            if member is None:
                try:
                    member = await message.guild.fetch_member(appeal["target_user_id"])
                    self.cached_members[member.id] = member
                except discord.NotFound:
                    member = None 
                except discord.Forbidden:
                    member = None 
                except discord.HTTPException:
                    member = None

            if member is None:
                await message.add_reaction("❌")
                await message.reply("This member is no longer in the server. The appeal can be safely rejected.")
                return

            try:
                await member.send(
                    embed = discord.Embed(
                        title=f"Message From {message.guild.name}'s Staff Team",
                        color=16777215,
                        description=f'### > {self.strip_mention(message.content, message.guild.me.id)}',
                    )
                )

                await message.add_reaction("✅")
            except discord.Forbidden:
                await message.add_reaction("❌")
                await message.reply("This member is no longer in the server. The appeal can be safely rejected.")
            
        else:
            appeal = await bot_db.get_current_active_appeal(message.author.id)
            if appeal is None:
                return

            webhook_url = await bot_db.get_webhook(
                appeal["guild_id"],
                "moderation_appeal_dm",
            )
            if webhook_url is None:
                return

            webhook = discord.Webhook.from_url(
                webhook_url,
                client=self.bot,
            )

            kwargs = {
                "content": message.content,
                "thread": discord.Object(id=appeal["thread_id"]),
                "username": message.author.name,
                "avatar_url": message.author.display_avatar.url,
                "allowed_mentions": discord.AllowedMentions.none(),
            }

            if message.attachments:
                kwargs["files"] = [
                    await attachment.to_file()
                    for attachment in message.attachments
                ]

            await webhook.send(**kwargs)

    mod = app_commands.Group(
        name = "mod",
        description = "Moderation Command Hierarchy"
    )

    case = app_commands.Group(
        name="case",
        description="Case management commands"
    )

    appeal = app_commands.Group(
        name="appeal",
        description="Moderation appeal commands"
    )

    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    @commands.command(name='ban', description='Ban a user from the server', aliases=['b'])
    @permission(command_name="ban")
    async def ban(self, ctx: commands.Context, member: discord.User | discord.Member | None = None, *, reason="No reason provided"):
        if not member:
            return await ctx.reply(
                view=CommandInfo(ctx, "Ban", ["ban user reason", f"ban {ctx.me.mention} Toxicity!", f"b {ctx.me.mention} Not obeying rules!"])
            )
        
        return await ctx.reply(
            embed=simple_embed("This command doesn't works, Try again later", 'cross')
        )

        await ctx.defer()

        attachments = (ctx.message.attachments if ctx.message else [])

        proofs = [
            att for att in attachments
            if att.content_type and att.content_type.startswith(("image/", "video/"))
        ]

        target_user = await self.resolve_user(ctx, member)
        if not target_user:
            return

        await ban_user(self.bot_db, self.logging_controller, ctx, target_user, reason, proofs)

    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    @commands.command(name='quarantine', description='Quarantines an user from this server', aliases=['jail', 'j', 'q'])
    @permission(command_name="quarantine")
    async def quarantine(self, ctx: commands.Context, member: discord.Member | discord.User | None = None, *, reason="No reason provided"):
        if not member:
            return await ctx.reply(
                view=CommandInfo(ctx, "Quarantine", ["quarantine user reason", f"j {ctx.me.mention} Toxicity!", f"q {ctx.me.mention} Not obeying rules" , f"quarantine {ctx.me.mention} breaking server rules",f"jail {ctx.me.mention} Toxicity!"])
            )

        await ctx.defer()

        attachments = (ctx.message.attachments if ctx.message else [])

        proofs = [
            att for att in attachments
            if att.content_type and att.content_type.startswith(("image/", "video/"))
        ]

        await quarantine_user(ctx, member, reason, proofs)


    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    @commands.command(name='unban', description='Unban a Particular User', aliases=['ub'])
    @permission(command_name="unban")
    async def unban(self, ctx, user: discord.User | None = None, * ,reason: str="No reason provided"):
        if user is None:
            await ctx.reply(view=CommandInfo(ctx, "Unban", ["unban user", f"unban {ctx.me.mention} Appealed", f"ub {ctx.me.mention} Appealed"]))
            return
        
        await unban_fn(ctx, user, reason)

    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    @commands.command(name='release', description='Release a member from quarantine', aliases=['qr', 'r'])
    @permission(command_name="unban")
    async def release(self, ctx, user: discord.Member | None =None, * ,reason: str="No reason provided"):
        if user is None:
            await ctx.reply(view=CommandInfo(ctx, "Release", ["release user reason", f"release {ctx.me.mention} Appealed", f"qr {ctx.me.mention} Appealed", f'r {ctx.me.mention} Appealed!']))
            return
        
        await release_fn(ctx, user, reason)

    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    @commands.command(name='mute', description='Mute a user with desired input', aliases=['m'])
    @permission(command_name="mute")
    async def mute(self, ctx:commands.Context, member:discord.Member | discord.User | None = None, duration:str="1",*, reason="No reason provided"):
        await ctx.defer()

        if member is None:
            await ctx.reply(view=CommandInfo(ctx, "Mute", ["mute user time reason", f"mute {ctx.me.mention} 3d Not Obeying Rules", f"mute {ctx.me.mention} 22hr Toxicity!"]))
            return

        proofs = [att for att in ctx.message.attachments if att.content_type and any(att.content_type.startswith(t) for t in ["image/", "video/"])]
        await mute_user(ctx, member, duration, reason, proofs)

    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    @commands.command(name='warn', description='Warn a user with a specific reason')
    @permission(command_name="warn")
    async def warn(self, ctx:commands.Context, member:discord.Member | discord.User | None = None,*, reason="No reason provided"):
        await ctx.defer()
        if member is None:
            await ctx.reply(view=CommandInfo(ctx, "Warn", ["warn user reason", f"warn {ctx.me.mention} Not Obeying Rules!"]))
            return
        proofs = [att for att in ctx.message.attachments if att.content_type and any(att.content_type.startswith(t) for t in ["image/", "video/"])]
        await warn_fn(ctx, member, reason, proofs)

    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    @commands.hybrid_command(name='unmute', description='unmutes a user with desired input')
    @permission(command_name="unmute")
    async def unmute(self, ctx: commands.Context, member: discord.Member | discord.User | None =None, *, reason: str="No reason provided"):
        if member is None:
            return await ctx.reply(
                view=CommandInfo(ctx, "Unmute", ["unmute user reason", f"unmute {ctx.me.mention} Appealed"])
            )

        await ctx.defer()
        await unmute_fn(ctx, member, reason)

    @mod.command(name='stats', description='checks stats for a particular moderator or yourself')
    @app_permission(command_name="ms")
    async def ms(self, interaction: discord.Interaction, member: discord.Member | discord.User | None = None, page_start: int = 0, page_end: int = 0):
        user = member or interaction.user

        await ms_fn(
            interaction=interaction,
            moderator=user,
            page_start=page_start,
            page_end=page_end
        )


    @case.command(name='list', description='Checks case logs for a particular user')
    @app_permission(command_name="modlogs")
    async def modlogs(
        self,
        interaction: discord.Interaction,
        member: discord.User | discord.Member | None = None,
        mod_type: ModType = ModType.All,
        moderator: discord.User | discord.Member | None = None
    ):
        target_id = member.id if member else interaction.user.id

        try:
            user = await self.bot.fetch_user(target_id)
        except Exception:
            return

        try:
            await mod_logs(
                interaction,
                target_user_id=target_id,
                user=user,
                moderator=moderator,
                mod_type=mod_type.value
            )

        except Exception as e:
            print(f"Exception [ModLogs] : {e}")

    @mod.command(name='insights', description='Get detailed moderation insights')
    @app_permission(command_name="moderation_insights")
    async def moderation_insights(self, interaction: discord.Interaction):
        await moderation_insights_fn(interaction)

    @case.command(name='edit', description='Edit a case')
    @app_permission(command_name="case_edit")
    async def case_edit(self, interaction: discord.Interaction, case_id: str, *, new_reason: str):
        if case_id is None or new_reason is None:
            return await interaction.response.send_message(
                view=CommandInfo(interaction, "Case Edit", ["edit_case case_id new_reason"])
            )

        await case_edit_fn(interaction, int(case_id), new_reason, False)

    @case.command(name='edit_absolute', description='Edit any case')
    @app_permission(command_name="case_edit_absolute")
    async def case_edit_absolute(self, interaction: discord.Interaction, case_id: int, *, new_reason: str):
        await case_edit_fn(interaction, case_id, new_reason, True)

    @case.command(name='delete', description='Delete a case')
    @app_permission(command_name="case_delete")
    async def case_delete(self, interaction: discord.Interaction, case_id: str):
        await case_delete_fn(interaction, int(case_id))

    @mod.command(name="acronym_add", description="Add an reason acronym")
    @app_permission(command_name = "mod_acronym_add")
    async def add_mod_acronym(self, interaction: discord.Interaction, key: str, * ,value: str):
        
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))
        
        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        await bot_db.add_moderation_acronym(interaction.user.id, interaction.guild.id, key, value)
        await interaction.response.send_message(embed=simple_embed(f"Successfully Added Moderation Acronym"))

    @mod.command(name="acronym_remove", description="Removes an reason acronym")
    @app_permission(command_name = "mod_acronym_remove")
    async def remove_mod_acronym(self, interaction: discord.Interaction, * ,key: str):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))
        
        bot_db: BotGlobalsDatabaseAccess = self.bot.db

        await bot_db.remove_moderation_acronym(interaction.user.id, interaction.guild.id, key)
        await interaction.response.send_message(embed=simple_embed(f"Successfully Removed Moderation Acronym"))

    @mod.command(name="acronym_update", description="Updates an reason acronym")
    @app_permission(command_name = "mod_acronym_update")
    async def update_mod_acronym(self, interaction: discord.Interaction, key: str, * ,value: str):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))
        
        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        await bot_db.update_moderation_acronym(interaction.user.id, interaction.guild.id, key, value)

        await interaction.response.send_message(embed=simple_embed(f"Successfully Updated Moderation Acronym"))

    @mod.command(name="acronyms", description="Display all moderation acronyms")
    @app_permission(command_name = "mod_acronyms")
    async def get_mod_acronym(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))
        
        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        result: dict[str, str] = await bot_db.get_moderation_acronyms(member.id if member is not None else interaction.user.id, interaction.guild.id)

        acronyms = ""
        for key, value in result.items():
            acronyms += f"- **{key}** : {value}\n"

        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Moderation Acronyms",
            description=acronyms,
            color=16777215
        )
        await interaction.response.send_message(embed=embed)

    @mod.command(name="acronym_transfer", description="Transfer an acronym to a members at a role")
    @app_permission(command_name = "mod_acronym_transfer")
    async def transfer_mod_acronym(self, interaction: discord.Interaction, target: discord.Member):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))
        
        bot_db: BotGlobalsDatabaseAccess = self.bot.db
        result: dict[str, str] = await bot_db.get_moderation_acronyms(interaction.user.id, interaction.guild.id)

        for key, value in result.items():
            await bot_db.add_moderation_acronym(target.id, interaction.guild.id, key, value)

        await interaction.response.send_message(embed=simple_embed(f"Successfully transferred moderation acronym to {target.mention}"))
     
    @appeal.command(name="setup", description="Setup Moderation Appeal for this server")
    @app_permission(command_name = "mod_appeal_management")
    async def setup_appeal(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))
        
        await setup_mod_appeal(interaction)

    @appeal.command(
        name="forum",
        description="Configure the appeal forum that users can fill out."
    )
    @app_permission(command_name="mod_appeal_management")
    async def configure_appeal_forum(
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
            AppealForumCustomize(self.bot.db)
        )

    @appeal.command(name="accept", description="Accept an appeal")
    @app_permission(command_name = "mod_appeal_handlers")
    async def accept_appeal(self, interaction: discord.Interaction):
        await accept_appeal_fn(interaction)

    @appeal.command(name="reject", description="Deny an appeal")
    @app_permission(command_name = "mod_appeal_handlers")
    async def reject_appeal(self, interaction: discord.Interaction, reason: str):
        await reject_appeal_fn(interaction, reason)


async def setup(bot):
    cog = LilyModeration(bot)
    await bot.add_cog(cog)