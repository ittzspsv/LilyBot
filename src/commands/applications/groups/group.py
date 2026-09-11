from discord import app_commands, Interaction

from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.application.controller import lily_application_controller as controller
from ..autocomplete import question_autocomplete, groups_autocomplete


class GroupCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="group", description="Application Groups")

    @app_permission(command_name="application_management")
    @app_commands.command(name="new", description="Create a new question group")
    @app_commands.autocomplete(
        question_1=question_autocomplete,
        question_2=question_autocomplete,
        question_3=question_autocomplete,
        question_4=question_autocomplete,
        question_5=question_autocomplete,
    )
    async def new(
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
        await controller.create_group(
            interaction,
            name,
            description,
            [question_1, question_2, question_3, question_4, question_5],
        )

    @app_permission(command_name="application_management")
    @app_commands.command(name="update", description="Update a existing question group")
    @app_commands.autocomplete(group=groups_autocomplete)
    async def update(self, interaction: Interaction, group: int, name: str, description: str):
        await controller.update_group(interaction, group, name, description)

    @app_permission(command_name="application_management")
    @app_commands.command(name="delete", description="Delete a existing question group")
    @app_commands.autocomplete(group=groups_autocomplete)
    async def delete(self, interaction: Interaction, group: int):
        await controller.delete_group(interaction, group)
