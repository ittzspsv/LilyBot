from typing import Optional, Any

from discord.ext import commands
from discord import Message, Thread, User
import discord

from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.configs.bot_details import emoji, img
from src.core.features.application.controller import lily_application_controller as controller
from src.core.features.application.components.lily_application_components import (
    ApplicationView,
    ApplicationQuestionView,
)
from .groups.application import ApplicationCommands

import logging
import re

logger = logging.getLogger("lily")


class LilyApplications(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db: Optional[BotGlobalsDatabaseAccess] = None
        self.app_group = ApplicationCommands()

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.app_group)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.app_group.name)

    async def on_load(self) -> None:
        self.db = self.bot.db

        """ Setup all views """
        if self.db is None:
            return
        views = await self.db.app_management_db.get_application_views()

        for view in views:
            _view = ApplicationView(
                self.db,
                view["channel_id"],
                view["application_id"],
                view["application"],
            )

            self.bot.add_view(_view, message_id=view["message_id"])
        print("Lily Applications Initialized!")

    async def _reply(self, message: Message, bot: Any) -> bool:
        ref = message.reference
        if ref is None:
            return False

        resolved = ref.resolved
        if isinstance(resolved, Message):
            return resolved.author.id == bot.user.id

        return False

    def strip_mention(self, content: str, bot_user_id: int) -> str:
        return re.sub(rf"<@!?{bot_user_id}>", "", content).strip()


    async def handle_application_answer(self, message: Message):
        if message.guild is not None:
            return
        
        if self.db is None:
            return

        
        submission = await self.db.app_management_db.get_pending_submission(
            message.author.id
        )

        if submission is None:
            return

        current_question = (
            await self.db.app_management_db.get_unanswered_application_question(
                submission["id"]
            )
        )
        if current_question is None:
            await message.channel.send(
                "Your application is already complete."
            )
            return

        if current_question["type"] in ('selector'):
            return

        await self.db.app_management_db.save_application_answer(
            submission_id=submission["id"],
            group_id=current_question["group_id"],
            question_id=current_question["id"],
            answer_value=message.content,
        )

        next_question = (
            await self.db.app_management_db.get_unanswered_application_question(
                submission["id"]
            )
        )

        if next_question is None:
            assert isinstance(message.author, User)
            await message.channel.send(
                "Your application has been submitted successfully. Thank you!"
            )
            await controller.push_submission(
                message.author,
                self.bot
            )
            await self.db.app_management_db.update_submission_status(
                submission["id"],
                "completed",
            )

            return

        await message.channel.send(
            view=ApplicationQuestionView(
                self.db,
                next_question,
            )
        )

    async def handle_applicant_remark(self, message: Message):
        if message.guild is None:
            return
        
        if not isinstance(message.channel, Thread):
            return

        is_mention = self.bot.user in message.mentions
        is_reply_to_bot = await self._reply(message, self.bot)

        if not (is_mention or is_reply_to_bot):
            return


        db: BotGlobalsDatabaseAccess = self.bot.db

        # Core logic.  
        result = await db.app_management_db.get_submission_thread_reference(message.channel.id)
        if result is None:
            logger.warning(
                "No submission thread reference found for thread=%s (invoked by user=%s)",
                message.channel.id, message.author.id,
            )
            return

        application = await db.app_management_db.get_application(message.guild.id, result["application_id"])
        if application is None:
            logger.error(
                "Application %s not found for guild=%s (thread=%s)",
                result["application_id"], message.guild.id, message.channel.id,
            )
            await message.reply(
                content="I can't find the application. I assume it might have been deleted?"
            )
            return

        member_id = result["member_id"]
        try:
            member = await message.guild.fetch_member(member_id)

            embed = discord.Embed(title=f"A remark has been added to {application["name"]}",
                    colour=0xffffff)

            embed.set_author(
                name=f"{message.guild.name}",
                icon_url=message.guild.icon.url if message.guild.icon else message.guild.me.display_avatar.url,
            )
            embed.add_field(
                name=f"{emoji["logs"]} Remark",
                value=f"- {self.strip_mention(message.content, message.guild.me.id)}",
                inline=False
            )
            embed.add_field(
                name=f"{emoji["clock"]} Wave",
                value=f"- {application["current_wave"] + 1}",
                inline=False
            )

            embed.set_image(url=img["border"])
            embed.set_footer(text="Regards, Staff Team")


            await member.send(embed=embed)
            await message.add_reaction("✅")
        except discord.NotFound:
            logger.warning(
                "Member %s not found in guild=%s while sending remark",
                member_id, message.guild.id,
            )
            await message.add_reaction("❌")
        except discord.Forbidden:
            logger.warning(
                "Forbidden: cannot DM member=%s (guild=%s) — DMs likely closed",
                member_id, message.guild.id,
            )
            await message.add_reaction("❌")

        except Exception as e:
            logger.exception(
                "Unexpected error sending remark to member=%s (guild=%s): %s",
                member_id, message.guild.id, e,
            )

            await message.add_reaction("❌")

    

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.author.bot:
            return

        await self.handle_applicant_remark(message=message)
        await self.handle_application_answer(message=message)

        

    @commands.Cog.listener()
    async def on_thread_update(self, before: Thread, after: Thread):
        if self.db is None:
            return

        before_tags = set(before.applied_tags)
        after_tags = set(after.applied_tags)

        added = after_tags - before_tags

        if added:
            for tag in added:
                status = tag.name.lower().replace(" ", "_")
                await self.db.app_management_db.update_submission_verification_status(
                    after.id,
                    status,
                )

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction, error):
        print("App command error:", error)


async def setup(bot):
    cog = LilyApplications(bot)
    await bot.add_cog(cog)

    if hasattr(cog, "on_load"):
        await cog.on_load()
