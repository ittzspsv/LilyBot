from discord import app_commands, Interaction, TextChannel

from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.application.controller import lily_application_controller as controller
from ..autocomplete import applications_autocomplete
from .applicant import ApplicantCommands
from .question import QuestionCommands
from .wave import WaveCommands
from .group import GroupCommands


class ApplicationCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="application", description="Lily Application Management System")
        self.add_command(ApplicantCommands())
        self.add_command(QuestionCommands())
        self.add_command(WaveCommands())
        self.add_command(GroupCommands())

    @app_permission(command_name="application_management")
    @app_commands.command(name="new", description="Create a new application form")
    async def new(self, interaction: Interaction):
        await controller.create_application(interaction)

    @app_permission(command_name="application_management")
    @app_commands.command(name="update", description="Update an application")
    @app_commands.autocomplete(application=applications_autocomplete)
    async def update(self, interaction: Interaction, application: int) -> None:
        await controller.update_application(interaction, application)

    @app_permission(command_name="application_management")
    @app_commands.command(name="send", description="Send an application view")
    @app_commands.autocomplete(application=applications_autocomplete)
    async def send(self, interaction: Interaction, application: int, channel: TextChannel):
        await controller.send_application_view(interaction, application, channel)

    @app_permission(command_name="application_management")
    @app_commands.command(name="delete", description="Delete an application")
    @app_commands.autocomplete(application=applications_autocomplete)
    async def delete(self, interaction: Interaction, application: int) -> None:
        await controller.delete_application(interaction, application)

    @app_permission(command_name="application_management")
    @app_commands.command(
        name="activate",
        description="Activate an application or deactivate an application",
    )
    @app_commands.autocomplete(application=applications_autocomplete)
    async def activate(self, interaction: Interaction, application: int, active: bool) -> None:
        await controller.set_active(interaction, application, active)

    @app_permission(command_name="application_management")
    @app_commands.command(name="invalidate", description="Removes all the pending submissions")
    @app_commands.autocomplete(application=applications_autocomplete)
    async def invalidate(self, interaction: Interaction, application: int):
        await controller.application_invalidate(interaction, application)

    @app_permission(command_name="application_flush", restrict=True)
    @app_commands.command(
        name="flush",
        description="Developer Only Utility for flushing all applications",
    )
    @app_commands.autocomplete(application=applications_autocomplete)
    async def flush(self, interaction: Interaction, application: int, wave: int):
        await controller.flush_submission(interaction, application, wave)
