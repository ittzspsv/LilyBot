from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.utils.lily_utility import length, truncate
from src.core.features.application.types.lily_application_types import QuestionType
from ..components.lily_application_components import CreateApplicationModal, ApplicationView, UpdateApplicationModal

from discord import Interaction, app_commands, TextChannel, User, Embed, ForumChannel
import discord
import json
import asyncio
import logging
from io import BytesIO
from discord.ext import commands
from src.core.configs.bot_details import img
from typing import Optional, List, Dict, Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from src.lily import Lily


logger = logging.getLogger("lily")


async def create_application(interaction: Interaction):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        application_groups: List[Dict[str, Any]] = await bot_db.app_management_db.get_groups_by_guild(interaction.guild.id)
    except Exception:
        logger.exception(
            "Failed to fetch application groups for guild %s while opening create_application modal",
            interaction.guild.id,
        )
        raise

    try:
        await interaction.response.send_modal(CreateApplicationModal(bot_db, application_groups[:25]))
    except Exception:
        logger.exception(
            "Failed to send CreateApplicationModal for guild %s",
            interaction.guild.id,
        )
        raise

async def send_application_view(
        interaction: Interaction, 
        application_id: int,
        channel: TextChannel
    ):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        application: Dict[str, Any] | None = await bot_db.app_management_db.get_application(
            interaction.guild.id,
            application_id
        )
    except Exception:
        logger.exception(
            "Failed to fetch application %s for guild %s in send_application_view",
            application_id, interaction.guild.id,
        )
        raise

    if application is None:
        logger.warning(
            "send_application_view: application %s not found in guild %s",
            application_id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("Application not found.")

    view = ApplicationView(
        bot_db,
        channel.id,
        application_id,
        application        
    )

    try:
        message = await channel.send(view=view)
    except discord.Forbidden:
        logger.exception(
            "Missing permissions to send application view to channel %s (guild %s)",
            channel.id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("I don't have permission to send messages in that channel.")
    except discord.HTTPException:
        logger.exception(
            "Discord HTTP error sending application view to channel %s (guild %s)",
            channel.id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("Failed to send the application message due to a Discord error.")

    try:
        await bot_db.app_management_db.create_application_view(
            interaction.guild.id,
            channel.id,
            application_id,
            message.id
        )
    except Exception:
        logger.exception(
            "Failed to persist application view record (guild=%s, channel=%s, application=%s, message=%s)",
            interaction.guild.id, channel.id, application_id, message.id,
        )
        raise

    await interaction.response.send_message(embed=simple_embed(f"Successfully sent application to {channel.mention}"))

async def update_application(
        interaction: Interaction,
        application_id: int
    ):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        application = await bot_db.app_management_db.get_application(interaction.guild.id, application_id)
    except Exception:
        logger.exception(
            "Failed to fetch application %s for guild %s in update_application",
            application_id, interaction.guild.id,
        )
        raise

    if application is None:
        logger.warning(
            "update_application: application %s not found in guild %s",
            application_id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("Application not found.")

    try:
        await interaction.response.send_modal(UpdateApplicationModal(bot_db, application))
    except Exception:
        logger.exception(
            "Failed to send UpdateApplicationModal for application %s (guild %s)",
            application_id, interaction.guild.id,
        )
        raise

async def get_application(interaction: Interaction, application_id: int):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        application = await bot_db.app_management_db.get_application(interaction.guild.id, application_id)
    except Exception:
        logger.exception(
            "Failed to fetch application %s for guild %s in get_application",
            application_id, interaction.guild.id,
        )
        raise

    if application is None:
        logger.info(
            "get_application: application %s not found in guild %s",
            application_id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("Application not found.")

    await interaction.response.send_message(
        embed=simple_embed(
            f"**{application['name']}**\n"
            f"{application['description']}\n"
            f"-# Active: {bool(application['active'])} | Wave: {application['current_wave']}"
        )
    )

async def list_applications(interaction: Interaction, active_only: bool = False):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        applications = await bot_db.app_management_db.get_applications_by_guild(
            interaction.guild.id,
            active_only
        )
    except Exception:
        logger.exception(
            "Failed to fetch applications for guild %s (active_only=%s) in list_applications",
            interaction.guild.id, active_only,
        )
        raise

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
    interaction: Interaction,
    application_id: int,
    active: bool
):
    if interaction.guild is None:
        raise app_commands.CheckFailure(
            "This command can only be used in a server."
        )

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        result = await bot_db.app_management_db.set_active(
            interaction.guild.id,
            application_id,
            active
        )
    except Exception:
        logger.exception(
            "Failed to set active=%s for application %s (guild %s)",
            active, application_id, interaction.guild.id,
        )
        raise

    if not result["success"]:
        logger.warning(
            "set_active failed for application %s (guild %s): %s",
            application_id, interaction.guild.id, result.get("message"),
        )
        raise app_commands.CheckFailure(result["message"])

    try:
        application_view = await bot_db.app_management_db.get_application_with_view(
            interaction.guild.id,
            application_id
        )
    except Exception:
        logger.exception(
            "Failed to fetch application_with_view for application %s (guild %s)",
            application_id, interaction.guild.id,
        )
        raise
    assert application_view is not None

    response = result["message"] + "\n"

    if result["status"] == "activated":
        try:
            new_wave = await bot_db.app_management_db.advance_wave(
                interaction.guild.id,
                application_id
            )
        except Exception:
            logger.exception(
                "Failed to advance wave after activation for application %s (guild %s)",
                application_id, interaction.guild.id,
            )
            raise
        response += (
            f"Application wave has been advanced to {(new_wave or 0) + 1}"
        )

    try:
        application = await bot_db.app_management_db.get_application(
            interaction.guild.id,
            application_id
        )
    except Exception:
        logger.exception(
            "Failed to re-fetch application %s (guild %s) after set_active",
            application_id, interaction.guild.id,
        )
        raise
    assert application is not None

    updated_view = ApplicationView(
        bot_db,
        application_view["channel_id"],
        application_id,
        application
    )

    channel = interaction.guild.get_channel(application_view["channel_id"])
    if not isinstance(channel, discord.TextChannel):
        try:
            channel = await interaction.guild.fetch_channel(application_view["channel_id"])
        except discord.NotFound:
            logger.warning(
                "Application channel %s no longer exists (guild %s, application %s)",
                application_view["channel_id"], interaction.guild.id, application_id,
            )
            raise app_commands.CheckFailure("Application channel no longer exists.")
        except discord.Forbidden:
            logger.exception(
                "Missing permissions to fetch application channel %s (guild %s, application %s)",
                application_view["channel_id"], interaction.guild.id, application_id,
            )
            raise app_commands.CheckFailure("I don't have permission to access the application channel.")
        except discord.HTTPException:
            logger.exception(
                "Discord HTTP error fetching application channel %s (guild %s, application %s)",
                application_view["channel_id"], interaction.guild.id, application_id,
            )
            raise app_commands.CheckFailure("Failed to reach the application channel due to a Discord error.")

    if not isinstance(channel, discord.TextChannel):
        logger.warning(
            "Resolved channel %s is not a TextChannel (guild %s, application %s)",
            application_view["channel_id"], interaction.guild.id, application_id,
        )
        raise app_commands.CheckFailure("Application channel no longer exists.")

    try:
        message = await channel.fetch_message(application_view["message_id"])
        await message.edit(view=updated_view)
    except discord.NotFound:
        logger.warning(
            "Application message %s no longer exists in channel %s (guild %s, application %s)",
            application_view["message_id"], channel.id, interaction.guild.id, application_id,
        )
        raise app_commands.CheckFailure("The application message no longer exists.")
    except discord.Forbidden:
        logger.exception(
            "Missing permissions to fetch/edit application message %s in channel %s (guild %s)",
            application_view["message_id"], channel.id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("I don't have permission to update the application message.")
    except discord.HTTPException:
        logger.exception(
            "Discord HTTP error updating application message %s in channel %s (guild %s)",
            application_view["message_id"], channel.id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("Failed to update the application message due to a Discord error.")

    await interaction.response.send_message(
        embed=simple_embed(response)
    )

async def advance_wave(interaction: Interaction, application_id: int):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        new_wave = await bot_db.app_management_db.advance_wave(interaction.guild.id, application_id)
    except Exception:
        logger.exception(
            "Failed to advance wave for application %s (guild %s)",
            application_id, interaction.guild.id,
        )
        raise

    if new_wave is None:
        logger.info(
            "advance_wave: application %s not found in guild %s",
            application_id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("Application not found.")

    await interaction.response.send_message(
        embed=simple_embed(f"Advanced application to wave {new_wave}.")
    )

async def delete_application(interaction: Interaction, application_id: int):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        success = await bot_db.app_management_db.delete_application(interaction.guild.id, application_id)
    except Exception:
        logger.exception(
            "Failed to delete application %s (guild %s)",
            application_id, interaction.guild.id,
        )
        raise

    if success:
        await interaction.response.send_message(
            embed=simple_embed("Successfully deleted the application.")
        )
    else:
        logger.info(
            "delete_application: application %s not found in guild %s",
            application_id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("Application not found.")

""" Application Question Management """

async def create_question(
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

    if type in (QuestionType.Selector,):
        options = metadata 
        if not options:
            logger.warning(
                "create_question: Selector question rejected due to missing options/metadata (guild %s, label=%r)",
                interaction.guild.id, label,
            )
            raise app_commands.CheckFailure(
                "Selector / radio button questions require at least one option."
            )

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        result = await bot_db.app_management_db.create_question(
            interaction.guild.id,
            label,
            type,
            description,
            placeholder,
            min_length,
            max_length,
            metadata
        )
    except Exception:
        logger.exception(
            "Failed to create question (guild %s, label=%r, type=%r)",
            interaction.guild.id, label, type,
        )
        raise

    await interaction.response.send_message(
        embed=simple_embed(
            f"Successfully created question **#{result['id']}**."
        )
    )

async def get_question(interaction: Interaction, question_id: int):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        question = await bot_db.app_management_db.get_question(interaction.guild.id, question_id)
    except Exception:
        logger.exception(
            "Failed to fetch question %s (guild %s)",
            question_id, interaction.guild.id,
        )
        raise

    if question is None:
        logger.info(
            "get_question: question %s not found in guild %s",
            question_id, interaction.guild.id,
        )
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

async def list_questions(interaction: Interaction):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        questions = await bot_db.app_management_db.get_questions_by_guild(
            interaction.guild.id
        )
    except Exception:
        logger.exception(
            "Failed to fetch questions for guild %s",
            interaction.guild.id,
        )
        raise

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

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        success = await bot_db.app_management_db.update_question(
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
    except Exception:
        logger.exception(
            "Failed to update question %s (guild %s)",
            question_id, interaction.guild.id,
        )
        raise

    if success:
        await interaction.response.send_message(
            embed=simple_embed("Successfully updated question.")
        )
    else:
        logger.warning(
            "update_question reported failure for question %s (guild %s)",
            question_id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("Failed to update question.")

async def delete_question(interaction: Interaction, question_id: int):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        success = await bot_db.app_management_db.delete_question(interaction.guild.id, question_id)
    except Exception:
        logger.exception(
            "Failed to delete question %s (guild %s)",
            question_id, interaction.guild.id,
        )
        raise

    if success:
        await interaction.response.send_message(
            embed=simple_embed("Successfully deleted the question.")
        )
    else:
        logger.info(
            "delete_question: question %s not found in guild %s",
            question_id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("Question not found.")

""" Groups Management """
async def create_group(
        interaction: Interaction,
        name: str,
        description: str,
        question_ids: List[int | None]
    ):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        result = await bot_db.app_management_db.create_group(
            interaction.guild.id,
            name,
            description,
            question_ids
        )
    except Exception:
        logger.exception(
            "Failed to create group (guild %s, name=%r, question_ids=%s)",
            interaction.guild.id, name, question_ids,
        )
        raise

    await interaction.response.send_message(
        embed=simple_embed(
            f"Successfully created group **#{result['id']}** with {len(question_ids)} question(s)."
        )
    )

async def get_group(interaction: Interaction, group_id: int):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        group = await bot_db.app_management_db.get_group(interaction.guild.id, group_id)
    except Exception:
        logger.exception(
            "Failed to fetch group %s (guild %s)",
            group_id, interaction.guild.id,
        )
        raise

    if group is None:
        logger.info(
            "get_group: group %s not found in guild %s",
            group_id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("Group not found.")

    try:
        question_lines = "\n".join(
            f"{q['position'] + 1}. {q['label']}" for q in group["questions"]
        ) or "No questions assigned."
    except Exception:
        logger.exception(
            "Failed to render question list for group %s (guild %s)",
            group_id, interaction.guild.id,
        )
        question_lines = "No questions assigned."

    await interaction.response.send_message(
        embed=simple_embed(
            f"**#{group['id']}** {group['name']}\n"
            f"{group['description']}\n\n"
            f"**Questions:**\n{question_lines}"
        )
    )

async def list_groups(interaction: Interaction):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        groups = await bot_db.app_management_db.get_groups_by_guild(
            interaction.guild.id
        )
    except Exception:
        logger.exception(
            "Failed to fetch groups for guild %s",
            interaction.guild.id,
        )
        raise

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
        interaction: Interaction,
        group_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None
    ):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        success = await bot_db.app_management_db.update_group(
            interaction.guild.id,
            group_id,
            name,
            description
        )
    except Exception:
        logger.exception(
            "Failed to update group %s (guild %s)",
            group_id, interaction.guild.id,
        )
        raise

    if success:
        await interaction.response.send_message(
            embed=simple_embed("Successfully updated group.")
        )
    else:
        logger.warning(
            "update_group reported failure for group %s (guild %s)",
            group_id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("Failed to update group.")

async def set_group_questions(
        interaction: Interaction,
        group_id: int,
        question_ids: str
    ):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    try:
        parsed_ids = [int(qid.strip()) for qid in question_ids.split(",") if qid.strip()]
    except ValueError:
        logger.warning(
            "set_group_questions: invalid question_ids input %r (guild %s, group %s)",
            question_ids, interaction.guild.id, group_id,
        )
        raise app_commands.CheckFailure("question_ids must be a comma-separated list of numbers.")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        await bot_db.app_management_db.set_group_questions(
            interaction.guild.id,
            group_id,
            parsed_ids
        )
    except Exception:
        logger.exception(
            "Failed to set group questions for group %s (guild %s, question_ids=%s)",
            group_id, interaction.guild.id, parsed_ids,
        )
        raise

    await interaction.response.send_message(
        embed=simple_embed(
            f"Successfully updated group questions ({len(parsed_ids)} question(s))."
        )
    )

async def delete_group(interaction: Interaction, group_id: int):
    if interaction.guild is None:
        raise app_commands.CheckFailure("This command can be only executed inside an guild")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        success = await bot_db.app_management_db.delete_group(interaction.guild.id, group_id)
    except Exception:
        logger.exception(
            "Failed to delete group %s (guild %s)",
            group_id, interaction.guild.id,
        )
        raise

    if success:
        await interaction.response.send_message(
            embed=simple_embed("Successfully deleted the group.")
        )
    else:
        logger.info(
            "delete_group: group %s not found in guild %s",
            group_id, interaction.guild.id,
        )
        raise app_commands.CheckFailure("Group not found.")

async def get_applicant_status(
    interaction: discord.Interaction,
    member: discord.Member | discord.User
):
    assert interaction.guild is not None

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        status = await bot_db.app_management_db.get_applicant_status(
            interaction.guild.id, member.id
        )
    except Exception:
        logger.exception(
            "Failed to fetch applicant status for member %s (guild %s)",
            member.id, interaction.guild.id,
        )
        raise

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

    try:
        json_bytes = json.dumps(applications, indent=2, default=str).encode("utf-8")
    except Exception:
        logger.exception(
            "Failed to serialize applicant status JSON for member %s (guild %s)",
            member.id, interaction.guild.id,
        )
        json_bytes = json.dumps({"error": "failed to serialize applications"}).encode("utf-8")

    file = discord.File(
        BytesIO(json_bytes),
        filename=f"applications_{member.id}.json",
    )

    try:
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)
    except discord.HTTPException:
        logger.exception(
            "Failed to send applicant status message for member %s (guild %s)",
            member.id, interaction.guild.id,
        )
        raise

async def applicant_entry_delete(
    interaction: Interaction,
    member: discord.Member | User,
    application: int
):
    assert interaction.guild is not None

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        _application = await bot_db.app_management_db.get_application(interaction.guild.id, application)
    except Exception:
        logger.exception(
            "Failed to fetch application %s (guild %s) in applicant_entry_delete",
            application, interaction.guild.id,
        )
        raise

    if _application is None:
        logger.info(
            "applicant_entry_delete: application %s not found in guild %s",
            application, interaction.guild.id,
        )
        return

    wave = _application["current_wave"]

    try:
        application_submission = await bot_db.app_management_db.get_submission(
            interaction.guild.id,
            application,
            member.id,
            wave
        )
    except Exception:
        logger.exception(
            "Failed to fetch submission for member %s, application %s, wave %s (guild %s)",
            member.id, application, wave, interaction.guild.id,
        )
        raise

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
            logger.info(
                "applicant_entry_delete: submission thread %s already gone (guild %s, member %s)",
                submission_thread, interaction.guild.id, member.id,
            )
        except discord.Forbidden:
            logger.exception(
                "Missing permissions to delete submission thread %s (guild %s, member %s)",
                submission_thread, interaction.guild.id, member.id,
            )
        except discord.HTTPException:
            logger.exception(
                "Discord HTTP error deleting submission thread %s (guild %s, member %s)",
                submission_thread, interaction.guild.id, member.id,
            )

    try:
        success = await bot_db.app_management_db.delete_submission(
            interaction.guild.id,
            application_submission["id"],
            member.id,
            wave
        )
    except Exception:
        logger.exception(
            "Failed to delete submission %s for member %s (guild %s)",
            application_submission["id"], member.id, interaction.guild.id,
        )
        raise

    if success:
        await interaction.response.send_message(embed=simple_embed("Successfully Deleted Submission"))
    else:
        logger.warning(
            "applicant_entry_delete: delete_submission reported failure for submission %s (guild %s)",
            application_submission["id"], interaction.guild.id,
        )
        await interaction.response.send_message(embed=simple_embed("Failed to Delete Submission", 'cross'))

async def push_submission(user: User, bot: commands.Bot):
    bot_db = cast("Lily", bot).db
    assert bot_db is not None

    try:
        pending_submission: Dict[str, Any] | None = await bot_db.app_management_db.get_pending_submission(
            user.id
        )
    except Exception:
        logger.exception(
            "Failed to fetch pending submission for user %s",
            user.id,
        )
        return

    if pending_submission is None:
        return

    try:
        submission: Dict[str, Any] | None = await bot_db.app_management_db.get_submission_result(
            guild_id=pending_submission["guild_id"],
            submission_id=pending_submission["id"]
        )
    except Exception:
        logger.exception(
            "Failed to fetch submission result for pending submission %s (guild %s, user %s)",
            pending_submission.get("id"), pending_submission.get("guild_id"), user.id,
        )
        return

    if submission is None:
        logger.warning(
            "push_submission: submission result not found for pending submission %s (user %s)",
            pending_submission.get("id"), user.id,
        )
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

    try:
        guild = bot.get_guild(guild_id)
        if guild is None:
            guild = await bot.fetch_guild(guild_id)
    except discord.HTTPException:
        logger.exception(
            "Failed to fetch guild %s for push_submission (submission %s)",
            guild_id, submission_id,
        )
        return

    try:
        channel = guild.get_channel(submission_forum_id)
        if channel is None:
            channel = await guild.fetch_channel(submission_forum_id)
    except discord.NotFound:
        logger.error(
            "push_submission: submission forum channel %s not found (guild %s, submission %s)",
            submission_forum_id, guild_id, submission_id,
        )
        return
    except discord.Forbidden:
        logger.exception(
            "Missing permissions to fetch submission forum channel %s (guild %s, submission %s)",
            submission_forum_id, guild_id, submission_id,
        )
        return
    except discord.HTTPException:
        logger.exception(
            "Discord HTTP error fetching submission forum channel %s (guild %s, submission %s)",
            submission_forum_id, guild_id, submission_id,
        )
        return

    if not isinstance(channel, ForumChannel):
        logger.error(
            "Expected submission_forum_id %s to be a ForumChannel, got %s (guild %s, submission %s)",
            submission_forum_id, type(channel).__name__, guild_id, submission_id,
        )
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
        logger.exception(
            "Failed to fetch avatar file for user %s (submission %s) - continuing without it",
            user.id, submission_id,
        )
        avatar_file = None

    try:
        if tag is not None:
            try:
                allotted_thread = await forum_channel.create_thread(
                    name=f"{user.display_name.title()}'s Submission",
                    content=base_content,
                    applied_tags=[tag],
                    file=avatar_file if avatar_file is not None else discord.utils.MISSING,
                )
            except discord.Forbidden:
                # Let us assume this is most likely due to the discord guild has been limited
                allotted_thread = await forum_channel.create_thread(
                    name=f"{user.display_name.title()}'s Submission",
                    content=base_content,
                    applied_tags=[tag],
                )
        else:
            try:
                allotted_thread = await forum_channel.create_thread(
                    name=f"{user.display_name}'s Submission",
                    content=base_content,
                    file=avatar_file if avatar_file is not None else discord.utils.MISSING,
                )
            except discord.Forbidden:
                # Let us assume this is most likely due to the discord guild has been limited
                allotted_thread = await forum_channel.create_thread(
                    name=f"{user.display_name.title()}'s Submission",
                    content=base_content                
                )
    except discord.Forbidden:
        logger.exception(
            "Missing permissions to create submission thread in forum %s (guild %s, submission %s)",
            forum_channel.id, guild_id, submission_id,
        )
        return
    except discord.HTTPException:
        logger.exception(
            "Discord HTTP error creating submission thread in forum %s (guild %s, submission %s)",
            forum_channel.id, guild_id, submission_id,
        )
        return

    forum_thread: discord.Thread = allotted_thread.thread

    try:
        await bot_db.app_management_db.set_submission_thread_reference(
            submission_id,
            forum_thread.id
        )
    except Exception:
        logger.exception(
            "Failed to persist submission_thread_reference for submission %s (thread %s)",
            submission_id, forum_thread.id,
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
        except Exception:
            logger.exception(
                "Failed to build/send group embed %r for submission %s (thread %s)",
                group.get("name"), submission_id, forum_thread.id,
            )

    if flag == 1:
        file_content = "\n".join(full_text)

        file = discord.File(
            BytesIO(file_content.encode("utf-8")),
            filename="application.txt"
        )

        try:
            await forum_thread.send(
                content="Some answers exceeded Discord's embed limit. They are attached below",
                file=file
            )
        except discord.HTTPException:
            logger.exception(
                "Failed to send overflow answers file for submission %s (thread %s)",
                submission_id, forum_thread.id,
            )


async def update_applicant(
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
        logger.warning(
            "update_applicant: invalid update action %r (guild %s, member %s)",
            update, interaction.guild.id, member_id,
        )
        raise app_commands.CheckFailure("Invalid update action.")

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        await bot_db.app_management_db.update_applicant(
            interaction.guild.id,
            member_id,
            interaction.user.id,
            update,
            reason,
        )
    except Exception:
        logger.exception(
            "Failed to update applicant %s (guild %s, action=%s)",
            member_id, interaction.guild.id, update,
        )
        raise

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
    interaction: Interaction,
    application: int,
):
    assert interaction.guild is not None

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    try:
        targeted = await bot_db.app_management_db.get_pending_submissions(
            interaction.guild.id,
            application_id=application
        )
    except Exception:
        logger.exception(
            "Failed to fetch pending submissions for application %s (guild %s)",
            application, interaction.guild.id,
        )
        raise

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
        try:
            deleted = await bot_db.app_management_db.delete_submission(
                guild_id=sub["guild_id"],
                submission_id=sub["submission_id"],
                member_id=sub["member_id"],
                wave=sub["wave"],
            )
        except Exception:
            logger.exception(
                "Failed to delete pending submission %s (guild %s, member %s) during invalidation",
                sub.get("submission_id"), sub.get("guild_id"), sub.get("member_id"),
            )
            continue

        if not deleted:
            continue

        invalidated_count += 1

        member = interaction.guild.get_member(sub["member_id"])
        if member is None:
            try:
                member = await interaction.guild.fetch_member(sub["member_id"])
            except discord.NotFound:
                logger.info(
                    "application_invalidate: member %s no longer in guild %s",
                    sub["member_id"], interaction.guild.id,
                )
                dm_failures.append(sub["member_id"])
                continue
            except discord.HTTPException:
                logger.exception(
                    "Discord HTTP error fetching member %s (guild %s) during invalidation",
                    sub["member_id"], interaction.guild.id,
                )
                dm_failures.append(sub["member_id"])
                continue

        try:
            await member.send(
                f"Your application for **{sub['application_name']}** has timed out and "
                f"was invalidated. You're welcome to apply again."
            )
        except discord.Forbidden:
            logger.info(
                "application_invalidate: could not DM member %s (DMs disabled/blocked)",
                sub["member_id"],
            )
            dm_failures.append(sub["member_id"])
        except discord.HTTPException:
            logger.exception(
                "Discord HTTP error DMing member %s during invalidation",
                sub["member_id"],
            )
            dm_failures.append(sub["member_id"])

        await asyncio.sleep(0.5)

    summary = f"Invalidated {invalidated_count} pending submission(s) for this application."
    if dm_failures:
        summary += f"\nCouldn't DM {len(dm_failures)} member(s) (DMs disabled or left the server)."

    await interaction.followup.send(summary, ephemeral=True)