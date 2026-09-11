import discord
from discord.ext import commands
from typing import Any, Dict
import re
import random

from src.core.utils.components.sLIlyGlobalComponents import CommandInfo
from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.features.permissions.lily_permissions import permission
from src.core.features.permissions.lily_permissions import has_permission
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.logging.lily_logging import LilyLoggingController
from src.core.features.moderation.components.lily_moderation_components import AppealMessageView

from src.core.features.moderation.controller.lily_moderation_controller import (
    ban_user,
    quarantine_user,
    mute_user,
    unmute as unmute_fn,
    unban as unban_fn,
    release as release_fn,
    warn as warn_fn,
)

from .groups import *


class LilyModeration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cached_members: Dict[int, discord.Member] = {}

        self.mod_group = ModCommands()
        self.case_group = CaseCommands()
        self.appeal_group = AppealCommands()

    @property
    def bot_db(self) -> BotGlobalsDatabaseAccess:
        return self.bot.db

    @property
    def logging_controller(self) -> LilyLoggingController:
        return self.bot.logging_controller

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.mod_group)
        self.bot.tree.add_command(self.case_group)
        self.bot.tree.add_command(self.appeal_group)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.mod_group.name)
        self.bot.tree.remove_command(self.case_group.name)
        self.bot.tree.remove_command(self.appeal_group.name)

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

    async def evaluate_quarantine_bypass(self, message: discord.Message):
        bot_db: BotGlobalsDatabaseAccess = self.bot.db

        if not isinstance(message.guild, discord.Guild):
            return

        if not isinstance(message.author, discord.Member):
            return

        if message.author.top_role >= message.guild.me.top_role:
            return

        bypass, case_id = await bot_db.is_quarantine_bypassing(
            message.author.id,
            message.guild.id
        )

        if bypass:
            target_user = message.author
            _messages = [
                f"Eliminating {target_user.mention} for attempting to bypass Quarantine",
                f"The worst she can say is 'No'\nShe:- Proceeds to quaratine {target_user.mention} (Bypassing quarantine)",
                f"{target_user.mention} shall be eliminated for defying the Quarantine.",
                f"Someone as weak as {target_user.mention} attempting to bypass Quarantine.",
                f"Even someone as weak as {target_user.mention} thought they could bypass Quarantine."
            ]
            _message = await message.channel.send(random.choice(_messages))
            ctx = await self.bot.get_context(_message)
            await quarantine_user(ctx, target_user, f"Quarantine Bypass (Ref #{case_id})", [], True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        await self.evaluate_quarantine_bypass(message)
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

            ctx = await self.bot.get_context(message)
            if appeal["moderator_id"] != message.author.id and has_permission(ctx, "mod_appeal_management") is False:
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
                view = AppealMessageView(
                    f"{self.strip_mention(message.content, message.guild.me.id)}",
                    message.guild.name,
                    message.attachments
                )
                await member.send(
                    view=view
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


async def setup(bot):
    cog = LilyModeration(bot)
    await bot.add_cog(cog)
