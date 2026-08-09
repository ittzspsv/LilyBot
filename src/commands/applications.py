from discord.ext import commands
from discord import app_commands, Interaction, TextChannel, Message, User, Thread, Member
from typing import Optional, List
import json

from src.core.features.permissions.lily_permissions import app_permission
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.features.application.controller.lily_application_controller import LilyApplicationController
from src.core.features.application.types.lily_application_types import QuestionType
from src.core.features.application.components.lily_application_components import ApplicationView, ApplicationQuestionView

class LilyApplications(commands.Cog):
    app = app_commands.Group(
            name="application",
            description="Lily Application Management System"
        )
    
    applicant = app_commands.Group(
        name = "applicants",
        description="Application Applicants Management System",
        parent=app
    )
    
    question = app_commands.Group(
        name = "question",
        description="Application Questions Management System",
        parent=app
    )

    wave = app_commands.Group(
        name="wave",
        description="Application Waves",
        parent=app
    )

    group = app_commands.Group(
        name="group",
        description="Application Groups",
        parent=app
    )

    def __init__(self, bot):
        self.bot = bot
        self.db: Optional[BotGlobalsDatabaseAccess] = None
        self.controller: Optional[LilyApplicationController] = None

    async def applications_autocomplete(
        self,
        interaction: Interaction,
        current: str,
    ) -> List[app_commands.Choice[int]]:
        if interaction.guild is None:
            return []
        
        assert self.db is not None

        applications = await self.db.app_management_db.get_applications_by_guild(
            guild_id=interaction.guild.id
        )

        current = current.lower()

        return [
            app_commands.Choice(
                name=application["name"],
                value=application["id"],
            )
            for application in applications
            if current in application["name"].lower()
        ][:25]
    
    async def question_autocomplete(
        self,
        interaction: Interaction,
        current: str
    ) -> List[app_commands.Choice[int]]:
        db: Optional[BotGlobalsDatabaseAccess] = self.bot.db

        if db is None or interaction.guild is None:
            return []

        questions = await db.app_management_db.get_questions_by_guild(interaction.guild.id)

        return [
            app_commands.Choice(name=q["label"][:100], value=q["id"])
            for q in questions
            if current.lower() in q["label"].lower()
        ][:25]
    
    async def groups_autocomplete(
        self,
        interaction: Interaction,
        current: str
    ) -> List[app_commands.Choice[int]]:
        db: Optional[BotGlobalsDatabaseAccess] = self.bot.db

        if db is None or interaction.guild is None:
            return []

        questions = await db.app_management_db.get_groups_by_guild(interaction.guild.id)

        return [
            app_commands.Choice(name=q["name"][:100], value=q["id"])
            for q in questions
            if current.lower() in q["name"].lower()
        ][:25]

    async def on_load(self) -> None:
        self.db = self.bot.db
        self.controller = LilyApplicationController(self.bot.db, self.bot)

        """ Setup all views """
        if self.db is None:
            return
        views = await self.db.app_management_db.get_application_views()

        for view in views:
            print(view["application"])
            _view = ApplicationView(
                self.db,
                view["channel_id"],
                view["application_id"],
                view["application"]
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
            if self.controller is None:
                return
            
            assert isinstance(message.author, User)
            await message.channel.send(
                "Your application has been submitted successfully. Thank you!"
            )
            await self.controller.push_submission(
                message.author
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

    @app_permission(command_name="application_management")
    @app.command(name="new", description="Create a new application form")
    async def create_application(
        self, interaction: Interaction
    ):
        if self.controller is not None:
            await self.controller.create_application(interaction)

    @app_permission(command_name="application_management")
    @app.command(name="update", description="Update an application")
    @app_commands.autocomplete(application=applications_autocomplete)
    async def update_application(
        self, interaction: Interaction,
        application: int
    ) -> None:
        if self.controller is not None:
            await self.controller.update_application(interaction, application)

    @app_permission(command_name="application_management")
    @app.command(name="send", description="Send an application view")
    @app_commands.autocomplete(application=applications_autocomplete)
    async def send_application(
        self, interaction: Interaction,
        application: int,
        channel: TextChannel
    ):
        if self.controller is not None:
            await self.controller.send_application_view(interaction, application, channel)
 

    @app_permission(command_name="application_management")
    @app.command(name="delete", description="Delete an application")
    @app_commands.autocomplete(application=applications_autocomplete)
    async def delete_application(
            self, interaction: Interaction,
            application: int
    ) -> None:
        if self.controller is not None:
            await self.controller.delete_application(interaction, application)

    @app_permission(command_name="application_management")
    @app.command(name="activate", description="Activate an application or deactivate an application")
    @app_commands.autocomplete(application=applications_autocomplete)
    async def application_activate(
            self, interaction: Interaction,
            application: int,
            active: bool
    ) -> None:
        if self.controller is not None:
            await self.controller.set_active(interaction, application, active)

    @app_permission(command_name="application_management")
    @question.command(name="new", description="Create a new application question")
    async def create_new_question(
        self, interaction: Interaction,
        label: str,
        description: str | None = None,
        placeholder: str | None = None,
        type: QuestionType = QuestionType.ShortText,
        min_length: int  = 0,
        max_length: int  = 2046,
        options: str | None = None
    ):
        if self.controller is not None:
            await self.controller.create_question(
                interaction,
                label,
                type.value,
                description,
                placeholder,
                min_length,
                max_length,
                json.dumps({"options": options.split(",") if options is not None else []}))

    @app_permission(command_name="application_management")
    @question.command(name="update", description="Update an existing application question")
    @app_commands.autocomplete(question=question_autocomplete)
    async def update_existing_question(
        self, interaction: Interaction,
        question: int,
        label: str | None = None,
        description: str |  None = None,
        placeholder: str | None = None,
        type: QuestionType | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        options: str | None = None
    ):
        if self.controller is not None:
            await self.controller.update_question(
                interaction,
                question,
                label,
                description,
                placeholder,
                min_length,
                max_length,
                type.value if type is not None else None,
                json.dumps({"options": options.split(",")}) if options is not None else None
            )
     
    @app_permission(command_name="application_management")
    @group.command(name="new", description="Create a new question group")
    @app_commands.autocomplete(
        question_1=question_autocomplete,
        question_2=question_autocomplete,
        question_3=question_autocomplete,
        question_4=question_autocomplete,
        question_5=question_autocomplete,
    )
    async def create_group(
        self,
        interaction: Interaction,
        name: str,
        description: str,
        question_1: int,
        question_2: int | None = None,
        question_3: int | None = None,
        question_4: int | None = None,
        question_5: int | None = None,
    ):
        if self.controller is not None:
            await self.controller.create_group(
                interaction,
                name,
                description,
                [question_1, question_2, question_3, question_4, question_5]
            )

    @app_permission(command_name="application_management")
    @group.command(name="update", description="Update a existing question group")
    @app_commands.autocomplete(
        group=groups_autocomplete
    )

    async def update_group(
        self,
        interaction: Interaction,
        group: int,
        name: str,
        description: str,
    ):
        if self.controller is not None:
            await self.controller.update_group(
                interaction,
                group,
                name,
                description
            )

    @app_permission(command_name="application_management")
    @group.command(name="delete", description="Delete a existing question group")
    @app_commands.autocomplete(
        group=groups_autocomplete
    )
    async def delete_group(
        self,
        interaction: Interaction,
        group: int
    ):
        if self.controller is not None:
            await self.controller.delete_group(
                interaction,
                group
            )

    @app_permission(command_name="applicant_block_unblock")
    @applicant.command(name="block", description="Block an applicant (globally)")
    async def applicant_block(
        self,
        interaction: Interaction,
        member: Member | User,
        reason: str
    ):
       if self.controller is not None:
           await self.controller.update_applicant(
               interaction,
               member.id,
               "block",
               reason
           ) 

    @app_permission(command_name="applicant_block_unblock")
    @applicant.command(name="unblock", description="Unblock an applicant (globally)")
    async def applicant_unblock(
        self,
        interaction: Interaction,
        member: Member | User,
        reason: str
    ):
        if self.controller is not None:
           await self.controller.update_applicant(
               interaction,
               member.id,
               "unblock",
               reason
           )

    @app_permission(command_name="application_management")
    @app_commands.autocomplete(application=applications_autocomplete)
    @applicant.command(name="entrydelete", description="Delete an applicant's application entry")
    async def applicant_entry_delete(
        self,
        interaction: Interaction,
        member: Member | User,
        application: int
    ):
        if self.controller is not None:
            await self.controller.applicant_entry_delete(
                interaction,
                member,
                application
            )

    @app_permission(command_name="application_staff")
    @applicant.command(name="status", description="Show an applicant status")
    async def applicant_status(
        self,
        interaction: Interaction,
        member: Member | User
    ):
        if self.controller is not None:
            await self.controller.get_applicant_status(
                interaction,
                member
            )

    @app_permission(command_name="application_management")
    @app.command(name="invalidate", description="Removes all the pending submissions")
    @app_commands.autocomplete(application=applications_autocomplete)
    async def application_invalidate(
        self,
        interaction: Interaction,
        application: int,
    ):
        if self.controller is not None:
            await self.controller.application_invalidate(
                interaction,
                application
            )

async def setup(bot):
    cog = LilyApplications(bot)
    await bot.add_cog(cog)

    if hasattr(cog, "on_load"):
        await cog.on_load()