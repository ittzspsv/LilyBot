from ....database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.utils.lily_utility import length, truncate
from src.core.features.application.types.lily_application_types import QuestionType
from ..components.lily_application_components import CreateApplicationModal, ApplicationView, UpdateApplicationModal

from discord import Interaction, app_commands, TextChannel, User, Embed, ForumChannel
import discord
import json
import asyncio
from io import BytesIO
from discord.ext import commands
from src.core.configs.sBotDetails import img
from typing import Optional, List, Dict, Any


class LilyApplicationController:
    def __init__(self, bot_db: BotGlobalsDatabaseAccess, bot: commands.Bot) -> None:
        self.bot_db: BotGlobalsDatabaseAccess = bot_db
        self.bot: commands.Bot = bot

    """ Application Management """

    async def create_application(self, interaction: Interaction):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")
        
        application_groups: List[Dict[str, Any]] = await self.bot_db.app_management_db.get_groups_by_guild(interaction.guild.id)
        await interaction.response.send_modal(CreateApplicationModal(self.bot_db, application_groups[:25]))

    async def send_application_view(self, 
            interaction: Interaction, 
            application_id: int,
            channel: TextChannel
        ):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")
        
        application: Dict[str, Any] | None = await self.bot_db.app_management_db.get_application(
            interaction.guild.id,
            application_id
        )

        assert application is not None

        view = ApplicationView(
            self.bot_db,
            channel.id,
            application_id,
            application        
        )

        message = await channel.send(view=view)
        await self.bot_db.app_management_db.create_application_view(
            interaction.guild.id,
            channel.id,
            application_id,
            message.id
        )
        await interaction.response.send_message(embed=simple_embed(f"Successfully sent application to {channel.mention}"))

    async def update_application(
            self,
            interaction: Interaction,
            application_id: int
        ):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")
        
        application = await self.bot_db.app_management_db.get_application(interaction.guild.id, application_id)
        assert application is not None
        await interaction.response.send_modal(UpdateApplicationModal(self.bot_db, application))

    async def get_application(self, interaction: Interaction, application_id: int):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        application = await self.bot_db.app_management_db.get_application(interaction.guild.id,application_id)

        if application is None:
            raise app_commands.CheckFailure("Application not found.")

        await interaction.response.send_message(
            embed=simple_embed(
                f"**{application['name']}**\n"
                f"{application['description']}\n"
                f"-# Active: {bool(application['active'])} | Wave: {application['current_wave']}"
            )
        )

    async def list_applications(self, interaction: Interaction, active_only: bool = False):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        applications = await self.bot_db.app_management_db.get_applications_by_guild(
            interaction.guild.id,
            active_only
        )

        if not applications:
            await interaction.response.send_message(
                embed=simple_embed("No applications found for this server.")
            )
            return

        lines = [
            f"**#{app['id']}** {app['name']} "
            f"(Active: {bool(app['active'])}, Wave: {app['current_wave']})"
            for app in applications
        ]

        await interaction.response.send_message(
            embed=simple_embed("\n".join(lines))
        )

    async def set_active(
        self,
        interaction: Interaction,
        application_id: int,
        active: bool
    ):
        if interaction.guild is None:
            raise app_commands.CheckFailure(
                "This command can only be used in a server."
            )

        result = await self.bot_db.app_management_db.set_active(
            interaction.guild.id,
            application_id,
            active
        )

        if not result["success"]:
            raise app_commands.CheckFailure(result["message"])

        application_view = await self.bot_db.app_management_db.get_application_with_view(
            interaction.guild.id,
            application_id
        )
        assert application_view is not None

        response = result["message"] + "\n"

        if result["status"] == "activated":
            new_wave = await self.bot_db.app_management_db.advance_wave(
                interaction.guild.id,
                application_id
            )
            response += (
                f"Application wave has been advanced to {(new_wave or 0) + 1}"
            )

        application = await self.bot_db.app_management_db.get_application(
            interaction.guild.id,
            application_id
        )
        assert application is not None

        updated_view = ApplicationView(
            self.bot_db,
            application_view["channel_id"],
            application_id,
            application
        )

        channel = interaction.guild.get_channel(application_view["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            channel = await interaction.guild.fetch_channel(application_view["channel_id"])

        if not isinstance(channel, discord.TextChannel):
            raise app_commands.CheckFailure("Application channel no longer exists.")

        try:
            message = await channel.fetch_message(application_view["message_id"])
            await message.edit(view=updated_view)
        except discord.NotFound:
            raise app_commands.CheckFailure("The application message no longer exists.")

        await interaction.response.send_message(
            embed=simple_embed(response)
        )

    async def advance_wave(self, interaction: Interaction, application_id: int):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        new_wave = await self.bot_db.app_management_db.advance_wave(interaction.guild.id, application_id)

        if new_wave is None:
            raise app_commands.CheckFailure("Application not found.")

        await interaction.response.send_message(
            embed=simple_embed(f"Advanced application to wave {new_wave}.")
        )

    async def delete_application(self, interaction: Interaction, application_id: int):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        success = await self.bot_db.app_management_db.delete_application(interaction.guild.id, application_id)

        if success:
            await interaction.response.send_message(
                embed=simple_embed("Successfully deleted the application.")
            )

        else:
            raise app_commands.CheckFailure("Application not found.")
        
    """ Application Question Management """
    
    async def create_question(
        self,
        interaction: Interaction,
        label: str,
        type: str,
        description: Optional[str] = None,
        placeholder: Optional[str] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        metadata: Optional[str] = None
    ):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")
        
        if type in (QuestionType.Selector,) and not options:
                raise app_commands.CheckFailure(
                    "Selector / radio button questions require at least one option."
                )

        result = await self.bot_db.app_management_db.create_question(
            interaction.guild.id,
            label,
            type,
            description,
            placeholder,
            min_length,
            max_length,
            metadata
        )

        await interaction.response.send_message(
            embed=simple_embed(
                f"Successfully created question **#{result['id']}**."
            )
        )

    async def get_question(self, interaction: Interaction, question_id: int):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        question = await self.bot_db.app_management_db.get_question(interaction.guild.id, question_id)

        if question is None:
            raise app_commands.CheckFailure("Question not found.")

        await interaction.response.send_message(
            embed=simple_embed(
                f"**#{question['id']}** ({question['type']})\n"
                f"{question['label']}\n"
                f"-# Description: {question['description'] or 'None'}\n"
                f"-# Placeholder: {question['placeholder'] or 'None'}\n"
                f"-# Length: {question['min_length'] or 0}-{question['max_length'] or '∞'}\n"
                f"-# Multiline: {bool(question['multiline'])}\n"
                f"-# Metadata: {question['metadata'] or 'None'}"
            )
        )

    async def list_questions(self, interaction: Interaction):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        questions = await self.bot_db.app_management_db.get_questions_by_guild(
            interaction.guild.id
        )

        if not questions:
            await interaction.response.send_message(
                embed=simple_embed("No questions found for this server.")
            )
            return

        lines = [
            f"**#{q['id']}** ({q['type']}) {q['label']}"
            for q in questions
        ]

        await interaction.response.send_message(
            embed=simple_embed("\n".join(lines))
        )

    async def update_question(
            self,
            interaction: Interaction,
            question_id: int,
            label: Optional[str] = None,
            description: Optional[str] = None,
            placeholder: Optional[str] = None,
            min_length: Optional[int] = None,
            max_length: Optional[int] = None,
            type: Optional[str] = None,
            metadata: Optional[str] = None
        ):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        success = await self.bot_db.app_management_db.update_question(
            interaction.guild.id,
            question_id,
            label,
            description,
            placeholder,
            min_length,
            max_length,
            type,
            metadata
        )

        if success:
            await interaction.response.send_message(
                embed=simple_embed("Successfully updated question.")
            )

        else:
            raise app_commands.CheckFailure("Failed to update question.")

    async def delete_question(self, interaction: Interaction, question_id: int):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        success = await self.bot_db.app_management_db.delete_question(interaction.guild.id, question_id)

        if success:
            await interaction.response.send_message(
                embed=simple_embed("Successfully deleted the question.")
            )

        else:
            raise app_commands.CheckFailure("Question not found.")
        

    """ Groups Management """
    async def create_group(
            self,
            interaction: Interaction,
            name: str,
            description: str,
            question_ids: List[int | None]
        ):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        result = await self.bot_db.app_management_db.create_group(
            interaction.guild.id,
            name,
            description,
            question_ids
        )

        await interaction.response.send_message(
            embed=simple_embed(
                f"Successfully created group **#{result['id']}** with {len(question_ids)} question(s)."
            )
        )

    async def get_group(self, interaction: Interaction, group_id: int):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        group = await self.bot_db.app_management_db.get_group(interaction.guild.id, group_id)

        if group is None:
            raise app_commands.CheckFailure("Group not found.")

        question_lines = "\n".join(
            f"{q['position'] + 1}. {q['label']}" for q in group["questions"]
        ) or "No questions assigned."

        await interaction.response.send_message(
            embed=simple_embed(
                f"**#{group['id']}** {group['name']}\n"
                f"{group['description']}\n\n"
                f"**Questions:**\n{question_lines}"
            )
        )

    async def list_groups(self, interaction: Interaction):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        groups = await self.bot_db.app_management_db.get_groups_by_guild(
            interaction.guild.id
        )

        if not groups:
            await interaction.response.send_message(
                embed=simple_embed("No groups found for this server.")
            )
            return

        lines = [
            f"**#{g['id']}** {g['name']} - {g['description']}"
            for g in groups
        ]

        await interaction.response.send_message(
            embed=simple_embed("\n".join(lines))
        )

    async def update_group(
            self,
            interaction: Interaction,
            group_id: int,
            name: Optional[str] = None,
            description: Optional[str] = None
        ):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        success = await self.bot_db.app_management_db.update_group(
            interaction.guild.id,
            group_id,
            name,
            description
        )

        if success:
            await interaction.response.send_message(
                embed=simple_embed("Successfully updated group.")
            )

        else:
            raise app_commands.CheckFailure("Failed to update group.")

    async def set_group_questions(
            self,
            interaction: Interaction,
            group_id: int,
            question_ids: str
        ):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        try:
            parsed_ids = [int(qid.strip()) for qid in question_ids.split(",") if qid.strip()]
        except ValueError:
            raise app_commands.CheckFailure("question_ids must be a comma-separated list of numbers.")

        await self.bot_db.app_management_db.set_group_questions(
            interaction.guild.id,
            group_id,
            parsed_ids
        )

        await interaction.response.send_message(
            embed=simple_embed(
                f"Successfully updated group questions ({len(parsed_ids)} question(s))."
            )
        )

    async def delete_group(self, interaction: Interaction, group_id: int):
        if interaction.guild is None:
            raise app_commands.CheckFailure("This command can be only executed inside an guild")

        success = await self.bot_db.app_management_db.delete_group(interaction.guild.id, group_id)

        if success:
            await interaction.response.send_message(
                embed=simple_embed("Successfully deleted the group.")
            )

        else:
            raise app_commands.CheckFailure("Group not found.")

    async def get_applicant_status(
        self,
        interaction: discord.Interaction,
        member: discord.Member | discord.User
    ):
        assert interaction.guild is not None

        status = await self.bot_db.app_management_db.get_applicant_status(
            interaction.guild.id, member.id
        )

        block_status = status["block_status"]
        applications = status["applications"]

        embed = discord.Embed(
            title=f"{member.display_name}'s Status",
            color=16777215,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.set_image(url=img["border"])

        embed.add_field(
            name="Block Status",
            value="Blocked" if block_status["blocked"] else "Not Blocked",
            inline=False,
        )

        if block_status["blocked"]:
            blocked_by = f"<@{block_status['blocked_by']}>" if block_status["blocked_by"] else "Unknown"
            embed.add_field(name="Reason", value=block_status["reason"] or "No reason provided", inline=True)
            embed.add_field(name="Blocked By", value=blocked_by, inline=True)
            embed.add_field(name="Blocked At", value=block_status["blocked_at"] or "Unknown", inline=True)

        embed.set_footer(text="Full application data attached as JSON")

        json_bytes = json.dumps(applications, indent=2, default=str).encode("utf-8")
        file = discord.File(
            BytesIO(json_bytes),
            filename=f"applications_{member.id}.json",
        )

        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    async def applicant_entry_delete(
        self,
        interaction: Interaction,
        member: discord.Member | User,
        application: int
    ):

        assert interaction.guild is not None

        _application = await self.bot_db.app_management_db.get_application(interaction.guild.id, application)
        if _application is None:
            return
        
        wave = _application["current_wave"]
        application_submission = await self.bot_db.app_management_db.get_submission(
            interaction.guild.id,
            application,
            member.id,
            wave
        )

        if application_submission is None:
            await interaction.response.send_message(embed=simple_embed("This applicant has not submitted any application", 'cross'))
            return

        submission_thread: int | None = application_submission["submission_thread_reference"]
        if submission_thread:
            try:
                thread = await interaction.guild.fetch_channel(submission_thread)

                if isinstance(thread, discord.Thread):
                    await thread.delete()

            except discord.NotFound:
                pass
            except discord.Forbidden:
                pass

        success = await self.bot_db.app_management_db.delete_submission(
            interaction.guild.id,
            application_submission["id"],
            member.id,
            wave
        )

        if success:
            await interaction.response.send_message(embed=simple_embed("Successfully Deleted Submission"))

        else:
            await interaction.response.send_message(embed=simple_embed("Failed to Delete Submission", 'cross'))

    async def push_submission(self, user: User):
        pending_submission: Dict[str, Any] | None = await self.bot_db.app_management_db.get_pending_submission(
            user.id
        )

        if pending_submission is None:
            return

        submission: Dict[str, Any] | None = await self.bot_db.app_management_db.get_submission_result(
            guild_id=pending_submission["guild_id"], 
            submission_id=pending_submission["id"]
        )

        if submission is None:
            return

        guild_id = submission["submission"]["guild_id"]
        submission_id = submission["submission"]["id"]
        application_id = submission["submission"]["application_id"]
        member_id = submission["submission"]["member_id"]
        wave = submission["submission"]["wave"]
        status = submission["submission"]["status"]
        submitted_at = submission["submission"]["submitted_at"]

        app_name = submission["application"]["name"]
        app_description = submission["application"]["description"]
        submission_forum_id = submission["application"]["submission_forum_id"]

        groups = submission["groups"]

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            guild = await self.bot.fetch_guild(guild_id)


        channel = guild.get_channel(submission_forum_id)
        if channel is None:
            channel = await guild.fetch_channel(submission_forum_id)

        if not isinstance(channel, ForumChannel):
            raise TypeError(
                f"Expected submission_forum_id {submission_forum_id} to be a ForumChannel, "
                f"got {type(channel).__name__}"
            )

        forum_channel: ForumChannel = channel

        base_content: str = f"**Applicant**: {user.mention}\n**Applicant ID**: #{submission_id}\n**Wave**: {wave + 1}"

        tag = discord.utils.get(forum_channel.available_tags, name="Pending")
        avatar_file: discord.File | None = None
        try:
            avatar_file = await user.display_avatar.with_format("png").to_file(
                filename="profile.png"
            )
        except discord.HTTPException:
            avatar_file = None

        if tag is not None:
            allotted_thread = await forum_channel.create_thread(
                name=f"{user.display_name.title()}'s Submission",
                content=base_content,
                applied_tags=[tag],
                file=avatar_file if avatar_file is not None else discord.utils.MISSING,
            )
        else:
            allotted_thread = await forum_channel.create_thread(
                name=f"{user.display_name}'s Submission",
                content=base_content,
                file=avatar_file if avatar_file is not None else discord.utils.MISSING,
            )
        forum_thread: discord.Thread = allotted_thread.thread
        await self.bot_db.app_management_db.set_submission_thread_reference(
            submission_id,
            forum_thread.id
        )

        flag = 0
        full_text = []

        for group in groups:
            try:
                embed = discord.Embed(
                    title=group["name"],
                    description=f'- {group["description"]}',
                    color=16777215
                )

                embed.set_image(url=img["border"])
                group_questions = group["questions"]

                for i, question in enumerate(group_questions):
                    answer = question["answer"] or "**No Answer Provided**"

                    if length(answer) > 1024:
                        flag = 1

                        full_text.extend([
                            group["name"],
                            f'{i + 1}. {question["label"]}',
                            f'* {answer}',
                            ""
                        ])

                        answer = truncate(answer)

                    embed.add_field(
                        name=f'{i + 1}. {question["label"]}',
                        value=answer,
                        inline=False
                    )

                await forum_thread.send(embed=embed)
            except Exception as e:
                print(e)


        if flag == 1:
            file_content = "\n".join(full_text)

            file = discord.File(
                BytesIO(file_content.encode("utf-8")),
                filename="application.txt"
            )

            await forum_thread.send(
                content="Some answers exceeded Discord's embed limit. They are attached below",
                file=file
            )


    async def update_applicant(
        self,
        interaction: Interaction,
        member_id: int,
        update: str,
        reason: str | None = None,
    ) -> None:
        if interaction.guild is None:
            raise app_commands.CheckFailure(
                "This command can only be used in a server."
            )

        if update not in ("block", "unblock"):
            raise app_commands.CheckFailure("Invalid update action.")

        await self.bot_db.app_management_db.update_applicant(
            interaction.guild.id,
            member_id,
            interaction.user.id,
            update,
            reason,
        )

        action = "block" if update == "block" else "unblock"
        message = (
            f"Successfully {action}ed <@{member_id}> from submitting applications."
        )
        if update == "block" and reason:
            message += f"\n**Reason:** {reason}"

        await interaction.response.send_message(
            embed=simple_embed(message)
        )

    async def application_invalidate(
        self,
        interaction: Interaction,
        application: int,
    ):
        assert interaction.guild is not None

        targeted = await self.bot_db.app_management_db.get_pending_submissions(
            interaction.guild.id,
            application_id=application
        )

        if not targeted:
            await interaction.response.send_message(
                embed=simple_embed("There are no pending submissions for that application.", 'warn'),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        invalidated_count = 0
        dm_failures = []

        for sub in targeted:
            deleted = await self.bot_db.app_management_db.delete_submission(
                guild_id=sub["guild_id"],
                submission_id=sub["submission_id"],
                member_id=sub["member_id"],
                wave=sub["wave"],
            )

            if not deleted:
                continue

            invalidated_count += 1

            member = interaction.guild.get_member(sub["member_id"])
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(sub["member_id"])
                except discord.NotFound:
                    dm_failures.append(sub["member_id"])
                    continue

            try:
                await member.send(
                    f"Your application for **{sub['application_name']}** has timed out and "
                    f"was invalidated. You're welcome to apply again."
                )
            except discord.Forbidden:
                dm_failures.append(sub["member_id"])

            await asyncio.sleep(0.5)

        summary = f"Invalidated {invalidated_count} pending submission(s) for this application."
        if dm_failures:
            summary += f"\nCouldn't DM {len(dm_failures)} member(s) (DMs disabled or left the server)."

        await interaction.followup.send(summary, ephemeral=True)