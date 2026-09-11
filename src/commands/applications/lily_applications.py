from typing import Optional

from discord.ext import commands
from discord import Message, Thread, User

from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.features.application.controller import lily_application_controller as controller
from src.core.features.application.components.lily_application_components import (
    ApplicationView,
    ApplicationQuestionView,
)
from .groups.application import ApplicationCommands


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

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.author.bot:
            return

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
