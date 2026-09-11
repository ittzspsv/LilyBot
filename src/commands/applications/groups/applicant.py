from discord import app_commands, Interaction, Member, User

from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.application.controller import lily_application_controller as controller
from ..autocomplete import applications_autocomplete


class ApplicantCommands(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="applicants",
            description="Application Applicants Management System",
        )

    @app_permission(command_name="applicant_block_unblock")
    @app_commands.command(name="block", description="Block an applicant (globally)")
    async def block(self, interaction: Interaction, member: Member | User, reason: str):
        await controller.update_applicant(interaction, member.id, "block", reason)

    @app_permission(command_name="applicant_block_unblock")
    @app_commands.command(name="unblock", description="Unblock an applicant (globally)")
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
