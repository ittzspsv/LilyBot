import json

from discord import app_commands, Interaction

from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.application.controller import lily_application_controller as controller
from src.core.features.application.types.lily_application_types import QuestionType
from ..autocomplete import question_autocomplete


class QuestionCommands(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="question",
            description="Application Questions Management System",
        )

    @app_permission(command_name="application_management")
    @app_commands.command(name="new", description="Create a new application question")
    async def new(
        self,
        interaction: Interaction,
        label: str,
        description: str | None = None,
        placeholder: str | None = None,
        type: QuestionType = QuestionType.ShortText,
        min_length: int = 0,
        max_length: int = 2046,
        options: str | None = None,
    ):
        await controller.create_question(
            interaction,
            label,
            type.value,
            description,
            placeholder,
            min_length,
            max_length,
            json.dumps({"options": options.split(",") if options is not None else []}),
        )

    @app_permission(command_name="application_management")
    @app_commands.command(name="update", description="Update an existing application question")
    @app_commands.autocomplete(question=question_autocomplete)
    async def update(
        self,
        interaction: Interaction,
        question: int,
        label: str | None = None,
        description: str | None = None,
        placeholder: str | None = None,
        type: QuestionType | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        options: str | None = None,
    ):
        await controller.update_question(
            interaction,
            question,
            label,
            description,
            placeholder,
            min_length,
            max_length,
            type.value if type is not None else None,
            json.dumps({"options": options.split(",")}) if options is not None else None,
        )
