from discord import app_commands, Interaction, TextChannel

from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.application.controller import lily_application_controller as controller
from src.core.features.application.components.lily_application_components import ApplicationMain
from ..autocomplete import applications_autocomplete
from .applicant import ApplicantCommands
from .wave import WaveCommands


class ApplicationCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="application", description="Lily Application Management System")
        self.add_command(ApplicantCommands())
        self.add_command(WaveCommands())

    @app_permission(
        command_name="application_management",
        permissions={"manage_guild"},
    )
    @app_commands.command(
        name="activate",
        description="Activate an application or deactivate an application",
    )
    @app_commands.describe(
        application="The application to activate or deactivate",
        active="True to activate, False to deactivate",
    )
    @app_commands.autocomplete(application=applications_autocomplete)
    async def activate(self, interaction: Interaction, application: int, active: bool) -> None:
        await controller.set_active(interaction, application, active)

    @app_permission(
        command_name="application_management",
        permissions={"manage_guild"},
    )
    @app_commands.command(name="invalidate", description="Removes all the pending submissions")
    @app_commands.describe(application="The application whose pending submissions should be removed")
    @app_commands.autocomplete(application=applications_autocomplete)
    async def invalidate(self, interaction: Interaction, application: int):
        await controller.application_invalidate(interaction, application)

    @app_permission(command_name="application_flush", restrict=True)
    @app_commands.command(
        name="flush",
        description="Developer Only Utility for flushing all applications",
    )
    @app_commands.describe(
        application="The application to flush",
        wave="The wave to flush submissions from",
    )
    @app_commands.autocomplete(application=applications_autocomplete)
    async def flush(self, interaction: Interaction, application: int, wave: int):
        await controller.flush_submission(interaction, application, wave)


    @app_permission(command_name="application_dashboard", restrict=True)
    @app_commands.command(
        name="dashboard",
        description="Open the application panel to setup"
    )
    @app_commands.guild_only()
    async def application_panel(self, interaction: Interaction):
        assert interaction.guild is not None
        await interaction.response.send_message(
            view=ApplicationMain(avatar_url=interaction.guild.me.display_avatar.url, in_place=True),
            ephemeral=True
        )