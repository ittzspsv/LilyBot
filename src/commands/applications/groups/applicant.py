from __future__ import annotations

from discord import app_commands, Interaction, Member, User
import discord

from src.core.features.permissions.lily_permissions import app_permission
from src.core.configs.bot_details import emoji
from src.core.features.application.controller import lily_application_controller as controller
from ..autocomplete import applications_autocomplete

from typing import cast, TYPE_CHECKING
import logging

logger = logging.getLogger("lily")

if TYPE_CHECKING:
    from src.lily import Lily


class ApplicantCommands(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="applicants",
            description="Application Applicants Management System",
        )

    @app_permission(command_name="applicant_block_unblock")
    @app_commands.command(name="block", description="Block an applicant (globally)")
    @app_commands.describe(member="Which member should be blocked")
    async def block(self, interaction: Interaction, member: Member | User, reason: str):
        await controller.update_applicant(interaction, member.id, "block", reason)

    @app_permission(command_name="applicant_block_unblock")
    @app_commands.command(name="unblock", description="Unblock an applicant (globally)")
    @app_commands.describe(member="Which member should be unblocked")
    async def unblock(self, interaction: Interaction, member: Member | User, reason: str):
        await controller.update_applicant(interaction, member.id, "unblock", reason)

    @app_permission(command_name="application_management")
    @app_commands.command(name="entrydelete", description="Delete an applicant's application entry")
    @app_commands.autocomplete(application=applications_autocomplete)
    async def entrydelete(
        self,
        interaction: Interaction,
        member: Member | User,
        application: int,
    ):
        await controller.applicant_entry_delete(interaction, member, application)

    @app_permission(command_name="application_staff")
    @app_commands.command(name="status", description="Show an applicant status")
    async def status(self, interaction: Interaction, member: Member | User):
        await controller.get_applicant_status(interaction, member)

    @app_permission(command_name="application_management")
    @app_commands.command(name="remark", description="Provide a remark for a applicant's submission")
    async def applicant_remark(self, interaction: Interaction, remark: str):
        db = cast("Lily", interaction.client).db
        assert db is not None

        if interaction.guild is None:
            await interaction.response.send_message(content="This command should be executed inside an guild")
            return

        assert interaction.channel is not None

        if not isinstance(interaction.channel, discord.Thread):
            logger.warning(
                "applicant_remark invoked outside a thread: user=%s channel=%s",
                interaction.user.id, interaction.channel.id,
            )
            await interaction.response.send_message(content=f"{interaction.user.mention} run this command inside an application forum", ephemeral=True)
            return

        result = await db.app_management_db.get_submission_thread_reference(interaction.channel.id)
        if result is None:
            logger.warning(
                "No submission thread reference found for thread=%s (invoked by user=%s)",
                interaction.channel.id, interaction.user.id,
            )
            await interaction.response.send_message(content=f"{interaction.user.mention} run this command inside an application forum. ", ephemeral=True)
            return

        application = await db.app_management_db.get_application(interaction.guild.id, result["application_id"])
        if application is None:
            logger.error(
                "Application %s not found for guild=%s (thread=%s)",
                result["application_id"], interaction.guild.id, interaction.channel.id,
            )
            await interaction.response.send_message(
                content="I can't find the application. I assume it might have been deleted?"
            )
            return

        member_id = result["member_id"]
        try:
            member = await interaction.guild.fetch_member(member_id)
            view = discord.ui.LayoutView().add_item(
                discord.ui.Container(
                    discord.ui.Section(
                        discord.ui.TextDisplay(content=f"## {emoji["logs"]} A remark has been added to **{application["name"]}**"),
                        discord.ui.TextDisplay(content=f"> ### {remark}"),
                        discord.ui.TextDisplay(content=f"{emoji["clock"]} **Wave**\n- {application["current_wave"] + 1}"),
                        accessory=discord.ui.Thumbnail(
                            media=interaction.guild.icon.url if interaction.guild.icon else interaction.guild.me.display_avatar.url,
                        ),
                    ),
                    discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                    discord.ui.TextDisplay(f"-# {emoji["staff"]} by {interaction.guild.name} Staff team.")
                )
            )

            await member.send(view=view)
            logger.info(
                "Sent remark to member=%s for application=%s (guild=%s)",
                member_id, application["name"], interaction.guild.id,
            )

            await interaction.response.send_message(f"I sent <@{member_id}> the remark you mentioned.")
        except discord.NotFound:
            logger.warning(
                "Member %s not found in guild=%s while sending remark",
                member_id, interaction.guild.id,
            )
            await interaction.response.send_message(content="I cannot fetch their User.", ephemeral=True)

        except discord.Forbidden:
            logger.warning(
                "Forbidden: cannot DM member=%s (guild=%s) — DMs likely closed",
                member_id, interaction.guild.id,
            )
            await interaction.response.send_message(content="I cannot Direct Message them.", ephemeral=True)

        except Exception as e:
            logger.exception(
                "Unexpected error sending remark to member=%s (guild=%s): %s",
                member_id, interaction.guild.id, e,
            )

