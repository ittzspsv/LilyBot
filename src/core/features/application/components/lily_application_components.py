from __future__ import annotations

import discord
import json
import logging

from typing import Dict, Any, List, cast,TYPE_CHECKING

from ....database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.configs.bot_details import emoji

if TYPE_CHECKING:
    from src.lily import Lily

logger = logging.getLogger("lily")


""" Application Dashboard """

class ApplicationMain(discord.ui.LayoutView):
    def __init__(self, avatar_url: str, in_place: bool = False) -> None:
        super().__init__(timeout=300 if in_place else None)

        self.in_place = in_place

        self.view_applications = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Manage",
            emoji=emoji["pencil"],
            custom_id="applications:view"
        )

        self.application_questions = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Manage",
            emoji=emoji["pencil"],
            custom_id="applications:questions"
        )

        self.application_groups = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Manage",
            emoji=emoji["pencil"],
            custom_id="applications:groups"
        )

        self.view_applications.callback = self.view_applications_callback
        self.application_questions.callback = self.application_questions_callback
        self.application_groups.callback = self.application_groups_callback

        self.add_item(
            discord.ui.Container(
                discord.ui.Section(
                    discord.ui.TextDisplay(content="## Application System Panel"),
                    discord.ui.TextDisplay(
                        content=(
                            "Create and manage staff applications in three steps:\n"
                            "- Create questions\n"
                            "- Organize questions into groups\n"
                            "- Create applications using selected groups"
                        )
                    ),
                    accessory=discord.ui.Thumbnail(media=avatar_url)
                ),

                discord.ui.Separator(),

                discord.ui.Section(
                    discord.ui.TextDisplay(content="### Application Questions"),
                    discord.ui.TextDisplay(
                        content="Create reusable questions for all applications."
                    ),
                    accessory=self.application_questions
                ),

                discord.ui.Separator(),

                discord.ui.Section(
                    discord.ui.TextDisplay(content="### Application Groups"),
                    discord.ui.TextDisplay(
                        content="Organize questions into groups with a title and description."
                    ),
                    accessory=self.application_groups
                ),

                discord.ui.Separator(),

                discord.ui.Section(
                    discord.ui.TextDisplay(content="### Applications"),
                    discord.ui.TextDisplay(
                        content="View and manage staff applications submitted on this server."
                    ),
                    accessory=self.view_applications
                )
            )
        )

    async def view_applications_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        data = await bot_db.app_management_db.get_applications_page(interaction.guild.id, 1)
        view = ApplicationsList(interaction.guild.id, data)

        if self.in_place:
            await interaction.response.edit_message(view=view)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    async def application_questions_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        data = await bot_db.app_management_db.get_questions_page(interaction.guild.id, 1)
        view = ApplicationsQuestionList(interaction.guild.id, data)

        if self.in_place:
            await interaction.response.edit_message(view=view)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    async def application_groups_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        data = await bot_db.app_management_db.get_groups_page(interaction.guild.id, 1)
        view = ApplicationsGroupList(interaction.guild.id, data)

        if self.in_place:
            await interaction.response.edit_message(view=view)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

class ApplicationsQuestionList(discord.ui.LayoutView):
    def __init__(self, guild_id: int, data: Dict[str, Any]) -> None:
        super().__init__(timeout=None)

        self.guild_id = guild_id
        self.page = data["page"]
        self.max_page = data["max_page"]
        self.questions = data["results"]

        items: List[discord.ui.Item] = []

        for question in self.questions:
            edit_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=emoji["pencil"],
                custom_id=str(question["id"]),
            )
            edit_button.callback = self.edit_callback

            items.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(content=f'**{question["label"]}**'),
                    discord.ui.TextDisplay(content=f'> {question["description"] or "No description provided"}'),
                    accessory=edit_button,
                )
            )

        if not items:
            items.append(discord.ui.TextDisplay(content="*No questions yet.*"))

        prev_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["left"],
            disabled=not data["has_prev"],
        )
        prev_button.callback = self.previous_callback

        page_indicator: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=f"Page {self.page}/{self.max_page}",
            disabled=True,
        )

        next_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["right"],
            disabled=not data["has_next"],
        )
        next_button.callback = self.next_callback

        back_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Back"
        )

        back_button.callback = self.back_callback

        self.add_item(discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content="### Application Questions\n- Create and manage questions that are shared"),
                accessory=back_button
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            *items,
            discord.ui.ActionRow(prev_button, page_indicator, next_button)
        ))


        add_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Add",
            emoji=emoji["plus"]
        )
        add_button.callback = self.add_callback

        remove_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Remove",
            disabled=not self.questions,
            emoji=emoji["trash"]
        )
        remove_button.callback = self.remove_callback

        self.add_item(discord.ui.ActionRow(add_button, remove_button))

    async def refresh(self, interaction: discord.Interaction, page: int) -> None:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        data = await bot_db.app_management_db.get_questions_page(self.guild_id, page)
        await interaction.response.edit_message(view=ApplicationsQuestionList(self.guild_id, data))

    async def previous_callback(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction, self.page - 1)

    async def next_callback(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction, self.page + 1)

    async def add_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(QuestionModal(self))

    async def remove_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RemoveQuestionModal(self))

    async def edit_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        assert interaction.custom_id is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        question = await bot_db.app_management_db.get_question(interaction.guild.id, int(interaction.custom_id))
        if question is None:
            await interaction.response.send_message(embed=simple_embed("Question not found", 'cross'), ephemeral=True)
            return

        await interaction.response.send_modal(QuestionModal(self, question))

    async def back_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.client.user is not None

        await interaction.response.edit_message(
            view=ApplicationMain(interaction.client.user.display_avatar.url, in_place=True)
        )

class QuestionModal(discord.ui.Modal):
    def __init__(self, list_view: ApplicationsQuestionList, question: Dict[str, Any] | None = None) -> None:
        super().__init__(title="Edit Question" if question else "Add Question")

        self.list_view = list_view
        self.question = question
        q = question or {}

        self.label_input = discord.ui.TextInput(
            label="Label",
            max_length=1000,
            default=q.get("label"),
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=1000,
            default=q.get("description"),
        )
        self.placeholder_input = discord.ui.TextInput(
            label="Placeholder",
            required=False,
            max_length=1000,
            default=q.get("placeholder"),
        )
        self.min_length_input = discord.ui.TextInput(
            label="Min Length",
            required=False,
            max_length=4,
            default=str(q["min_length"]) if q.get("min_length") is not None else None,
        )
        self.max_length_input = discord.ui.TextInput(
            label="Max Length",
            required=False,
            max_length=4,
            default=str(q["max_length"]) if q.get("max_length") is not None else None,
        )

        self.add_item(self.label_input)
        self.add_item(self.description_input)
        self.add_item(self.placeholder_input)
        self.add_item(self.min_length_input)
        self.add_item(self.max_length_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        min_text = self.min_length_input.value.strip()
        max_text = self.max_length_input.value.strip()

        if (min_text and not min_text.isdigit()) or (max_text and not max_text.isdigit()):
            await interaction.response.send_message(embed=simple_embed("Min and max length must be numbers.", 'cross'), ephemeral=True)
            return

        min_length = int(min_text) if min_text else None
        max_length = int(max_text) if max_text else None

        if min_length is not None and max_length is not None and min_length > max_length:
            await interaction.response.send_message(embed=simple_embed("Min length cannot be greater than max length.", 'cross'), ephemeral=True)
            return

        if self.question is None:
            await bot_db.app_management_db.create_question(
                interaction.guild.id,
                label=self.label_input.value,
                type="text",
                description=self.description_input.value or None,
                placeholder=self.placeholder_input.value or None,
                min_length=min_length,
                max_length=max_length,
            )
            # Out-of-range pages are clamped by the db, so this lands on the last page
            page = self.list_view.max_page + 1
        else:
            await bot_db.app_management_db.update_question(
                interaction.guild.id,
                self.question["id"],
                label=self.label_input.value,
                description=self.description_input.value,
                placeholder=self.placeholder_input.value,
                min_length=min_length,
                max_length=max_length,
            )
            page = self.list_view.page

        await self.list_view.refresh(interaction, page)

class RemoveQuestionModal(discord.ui.Modal):
    def __init__(self, list_view: ApplicationsQuestionList) -> None:
        super().__init__(title="Remove Question")

        self.list_view = list_view
        self.select = discord.ui.Select(
            placeholder="Select a question",
            options=[
                discord.SelectOption(label=q["label"][:100], value=str(q["id"]))
                for q in list_view.questions
            ],
        )
        self.add_item(discord.ui.Label(text="Question to remove", component=self.select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        await bot_db.app_management_db.delete_question(interaction.guild.id, int(self.select.values[0]))

        # A now-empty last page is clamped back by the db
        await self.list_view.refresh(interaction, self.list_view.page)

class ApplicationsGroupList(discord.ui.LayoutView):
    def __init__(self, guild_id: int, data: Dict[str, Any]) -> None:
        super().__init__(timeout=None)

        self.guild_id = guild_id
        self.page = data["page"]
        self.max_page = data["max_page"]
        self.groups = data["results"]

        items: List[discord.ui.Item] = []

        for group in self.groups:
            edit_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=emoji["pencil"],
                custom_id=str(group["id"]),
            )
            edit_button.callback = self.edit_callback

            content = f"**{group['name']}**"
            if group["description"]:
                content += f"\n> {group['description']}"

            items.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(content=content),
                    accessory=edit_button,
                )
            )

        if not items:
            items.append(discord.ui.TextDisplay(content="*No groups yet.*"))

        prev_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["left"],
            disabled=not data["has_prev"],
        )
        prev_button.callback = self.previous_callback

        page_indicator: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=f"Page {self.page}/{self.max_page}",
            disabled=True,
        )

        next_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["right"],
            disabled=not data["has_next"],
        )
        next_button.callback = self.next_callback

        back_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Back"
        )

        back_button.callback = self.back_callback


        self.add_item(discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content="### Application Groups\n- Create and manage groups of questions"),
                accessory=back_button
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            *items,
            discord.ui.ActionRow(prev_button, page_indicator, next_button)

        ))

        add_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Add",
            emoji=emoji["plus"]
        )
        add_button.callback = self.add_callback

        remove_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Remove",
            disabled=not self.groups,
            emoji=emoji["trash"]
        )
        remove_button.callback = self.remove_callback
        self.add_item(discord.ui.ActionRow(add_button, remove_button))

    async def refresh(self, interaction: discord.Interaction, page: int) -> None:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        data = await bot_db.app_management_db.get_groups_page(self.guild_id, page)
        await interaction.response.edit_message(view=ApplicationsGroupList(self.guild_id, data))

    async def previous_callback(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction, self.page - 1)

    async def next_callback(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction, self.page + 1)

    async def add_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        questions = await bot_db.app_management_db.get_questions_by_guild(interaction.guild.id)
        if not questions:
            await interaction.response.send_message(embed=simple_embed("Create a question first.", 'cross'), ephemeral=True)
            return

        await interaction.response.send_modal(GroupModal(self, questions[:25]))

    async def remove_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RemoveGroupModal(self))

    async def edit_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        assert interaction.custom_id is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        group = await bot_db.app_management_db.get_group(interaction.guild.id, int(interaction.custom_id))
        if group is None:
            await interaction.response.send_message(embed=simple_embed("Group not found", 'cross'), ephemeral=True)
            return

        current_ids = {q["id"] for q in group["questions"]}
        questions = await bot_db.app_management_db.get_questions_by_guild(interaction.guild.id)
        questions.sort(key=lambda q: q["id"] not in current_ids)

        await interaction.response.send_modal(GroupModal(self, questions[:25], group))

    async def back_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.client.user is not None

        await interaction.response.edit_message(
            view=ApplicationMain(interaction.client.user.display_avatar.url, in_place=True)
        )

class GroupModal(discord.ui.Modal):
    def __init__(
        self,
        list_view: ApplicationsGroupList,
        questions: List[Dict[str, Any]],
        group: Dict[str, Any] | None = None,
    ) -> None:
        super().__init__(title="Edit Group" if group else "Add Group")

        self.list_view = list_view
        self.questions = questions
        self.group = group

        current_ids = {q["id"] for q in group["questions"]} if group else set()

        self.name_input = discord.ui.TextInput(
            label="Name",
            max_length=100,
            default=group["name"] if group else None,
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=300,
            default=group["description"] if group else None,
        )
        self.select = discord.ui.Select(
            placeholder="Select 1 to 5 questions",
            min_values=1,
            max_values=min(5, len(questions)),
            options=[
                discord.SelectOption(
                    label=q["label"][:100],
                    value=str(q["id"]),
                    default=q["id"] in current_ids,
                )
                for q in questions
            ],
        )

        self.add_item(self.name_input)
        self.add_item(self.description_input)
        self.add_item(discord.ui.Label(text="Questions", component=self.select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        selected = {int(value) for value in self.select.values}
        question_ids = [q["id"] for q in self.questions if q["id"] in selected]

        if self.group is None:
            await bot_db.app_management_db.create_group(
                interaction.guild.id,
                self.name_input.value,
                self.description_input.value,
                question_ids,
            )
            page = self.list_view.max_page + 1
        else:
            await bot_db.app_management_db.update_group(
                interaction.guild.id,
                self.group["id"],
                name=self.name_input.value,
                description=self.description_input.value,
            )
            await bot_db.app_management_db.set_group_questions(
                interaction.guild.id,
                self.group["id"],
                question_ids,
            )
            page = self.list_view.page

        await self.list_view.refresh(interaction, page)

class RemoveGroupModal(discord.ui.Modal):
    def __init__(self, list_view: ApplicationsGroupList) -> None:
        super().__init__(title="Remove Group")

        self.list_view = list_view
        self.select = discord.ui.Select(
            placeholder="Select a group",
            options=[
                discord.SelectOption(label=g["name"][:100], value=str(g["id"]))
                for g in list_view.groups
            ],
        )
        self.add_item(discord.ui.Label(text="Group to remove", component=self.select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        await bot_db.app_management_db.delete_group(interaction.guild.id, int(self.select.values[0]))

        await self.list_view.refresh(interaction, self.list_view.page)

class ApplicationsList(discord.ui.LayoutView):
    def __init__(self, guild_id: int, data: Dict[str, Any]) -> None:
        super().__init__(timeout=None)

        self.guild_id = guild_id
        self.page = data["page"]
        self.max_page = data["max_page"]
        self.applications = data["results"]

        items: List[discord.ui.Item] = []

        for application in self.applications:
            edit_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Edit",
                custom_id=str(application["id"]),
            )
            edit_button.callback = self.edit_callback

            items.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=(
                            f"**#{application['id']}** {application['name']}\n"
                            f"-# Active: {bool(application['active'])} | Wave: {application['current_wave'] + 1}"
                        )
                    ),
                    accessory=edit_button,
                )
            )

        if not items:
            items.append(discord.ui.TextDisplay(content="*No applications yet.*"))

        prev_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["left"],
            disabled=not data["has_prev"],
        )
        prev_button.callback = self.previous_callback

        page_indicator: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=f"Page {self.page}/{self.max_page}",
            disabled=True,
        )

        next_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["right"],
            disabled=not data["has_next"],
        )
        next_button.callback = self.next_callback

        back_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Back"
        )

        back_button.callback = self.back_callback

        self.add_item(discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content="### Applications\n- Create and manage applications"),
                accessory=back_button
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            *items,
            discord.ui.ActionRow(prev_button, page_indicator, next_button)

        ))

        add_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Add",
            emoji=emoji["plus"]
        )
        add_button.callback = self.add_callback

        remove_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Remove",
            emoji=emoji["trash"],
            disabled=not self.applications,
        )
        remove_button.callback = self.remove_callback
        
        self.add_item(discord.ui.ActionRow(add_button, remove_button))

    async def refresh(self, interaction: discord.Interaction, page: int) -> None:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        data = await bot_db.app_management_db.get_applications_page(self.guild_id, page)


        view = ApplicationsList(self.guild_id, data)

        if interaction.response.is_done():
            await interaction.edit_original_response(view=view)
        else:
            await interaction.response.edit_message(view=view)

    async def previous_callback(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction, self.page - 1)

    async def next_callback(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction, self.page + 1)

    async def add_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        groups = await bot_db.app_management_db.get_groups_by_guild(interaction.guild.id)
        if not groups:
            await interaction.response.send_message(embed=simple_embed("Create a group first.", 'cross'), ephemeral=True)
            return

        await interaction.response.send_modal(ApplicationModal(self, groups[:25]))

    async def remove_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RemoveApplicationModal(self))

    async def edit_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        assert interaction.custom_id is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        application_id = int(interaction.custom_id)

        application = await bot_db.app_management_db.get_application(interaction.guild.id, application_id)
        if application is None:
            await interaction.response.send_message(embed=simple_embed("Application not found", 'cross'), ephemeral=True)
            return

        assigned = await bot_db.app_management_db.get_application_groups(interaction.guild.id, application_id)
        assigned_ids = [g["id"] for g in assigned]

        groups = await bot_db.app_management_db.get_groups_by_guild(interaction.guild.id)
        groups.sort(key=lambda g: assigned_ids.index(g["id"]) if g["id"] in assigned_ids else len(assigned_ids))

        await interaction.response.send_modal(ApplicationModal(self, groups[:25], application, assigned_ids))

    async def back_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.client.user is not None

        await interaction.response.edit_message(
            view=ApplicationMain(interaction.client.user.display_avatar.url, in_place=True)
        )   

class ApplicationModal(discord.ui.Modal):
    def __init__(
        self,
        list_view: ApplicationsList,
        groups: List[Dict[str, Any]],
        application: Dict[str, Any] | None = None,
        assigned_ids: List[int] | None = None,
    ) -> None:
        super().__init__(title="Edit Application" if application else "Add Application")

        self.list_view = list_view
        self.groups = groups
        self.application = application

        self.name_input = discord.ui.TextInput(
            label="Name",
            max_length=100,
            default=application["name"] if application else None,
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            default=application["description"] if application else None,
        )
        self.button_input = discord.ui.TextInput(
            label="Submit Button Label",
            max_length=80,
            default=application["submit_btn_label"] if application else "Apply",
        )
        self.group_select = discord.ui.Select(
            placeholder="Select the question groups",
            min_values=1,
            max_values=len(groups),
            options=[
                discord.SelectOption(
                    label=g["name"][:100],
                    value=str(g["id"]),
                    default=g["id"] in (assigned_ids or []),
                )
                for g in groups
            ],
        )

        self.add_item(self.name_input)
        self.add_item(self.description_input)
        self.add_item(self.button_input)
        self.add_item(discord.ui.Label(text="Groups", component=self.group_select))

        if application is None:
            self.forum_select = discord.ui.ChannelSelect(
                channel_types=[discord.ChannelType.forum],
                placeholder="Select the submission forum",
                min_values=1,
                max_values=1,
            )
            self.add_item(discord.ui.Label(text="Submission Forum", component=self.forum_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            logger.warning(
                "ApplicationModal.on_submit called outside of a guild (user_id=%s)",
                interaction.user.id if interaction.user else None,
            )
            raise discord.app_commands.CheckFailure("This command can only be executed inside a guild")

        await interaction.response.defer()

        bot_db = cast("Lily", interaction.client).db
        if bot_db is None:
            logger.error("Database is not available (guild_id=%s)", interaction.guild.id)
            await interaction.followup.send(
                embed=simple_embed("Database is not available. Please try again later.", 'cross'),
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id

        try:
            selected = {int(value) for value in self.group_select.values}
        except (TypeError, ValueError):
            logger.exception(
                "Failed to parse selected application group ids: %s",
                self.group_select.values,
            )
            await interaction.followup.send(
                embed=simple_embed("Invalid application group selection.", 'cross'),
                ephemeral=True,
            )
            return

        group_ids = [g["id"] for g in self.groups if g["id"] in selected]

        if self.application is None:
            forum = self.forum_select.values[0]

            try:
                application = await bot_db.app_management_db.create_application(
                    guild_id,
                    self.name_input.value,
                    self.description_input.value,
                    forum.id,
                    self.button_input.value,
                )
            except Exception:
                logger.exception(
                    "Failed to create application record in database for guild_id=%s",
                    guild_id,
                )
                await interaction.followup.send(
                    embed=simple_embed("Failed to save the application. Please try again later.", 'cross'),
                    ephemeral=True,
                )
                return

            try:
                await bot_db.app_management_db.assign_groups(
                    guild_id,
                    application["id"],
                    group_ids,
                )
            except Exception:
                logger.exception(
                    "Failed to assign groups %s to application_id=%s in guild_id=%s",
                    group_ids,
                    application["id"],
                    guild_id,
                )
                await interaction.followup.send(
                    embed=simple_embed(
                        "Application was created, but assigning question groups failed. "
                        "Edit the application to assign them again.",
                        'cross',
                    ),
                    ephemeral=True,
                )

            page = self.list_view.max_page + 1

        else:
            application_id = self.application["id"]

            try:
                success = await bot_db.app_management_db.update_application(
                    guild_id,
                    application_id,
                    application_name=self.name_input.value,
                    application_description=self.description_input.value,
                    submit_btn_label=self.button_input.value,
                    application_group_assignments=group_ids,
                )
            except Exception:
                logger.exception(
                    "Failed to update application_id=%s in guild_id=%s",
                    application_id,
                    guild_id,
                )
                await interaction.followup.send(
                    embed=simple_embed("Failed to update the application.", 'cross'),
                    ephemeral=True,
                )
                return

            if not success:
                logger.warning(
                    "update_application returned falsy success for application_id=%s in guild_id=%s",
                    application_id,
                    guild_id,
                )
                await interaction.followup.send(
                    embed=simple_embed("Failed to update the application.", 'cross'),
                    ephemeral=True,
                )
                return

            try:
                application_view = await bot_db.app_management_db.get_application_with_view(
                    guild_id, application_id
                )
                updated_application = await bot_db.app_management_db.get_application(
                    guild_id, application_id
                )
            except Exception:
                logger.exception(
                    "Failed to fetch application/view data for application_id=%s in guild_id=%s after update",
                    application_id,
                    guild_id,
                )
                application_view = None
                updated_application = None
                await interaction.followup.send(
                    embed=simple_embed(
                        "Application was updated, but refreshing the application message failed.",
                        'cross',
                    ),
                    ephemeral=True,
                )

            if application_view is not None and updated_application is not None:
                updated_view = ApplicationView(
                    bot_db,
                    application_view["channel_id"],
                    updated_application["id"],
                    updated_application,
                )

                try:
                    channel = interaction.guild.get_channel(application_view["channel_id"])
                    if channel is None:
                        channel = await interaction.guild.fetch_channel(application_view["channel_id"])

                    if not isinstance(channel, discord.TextChannel):
                        raise discord.NotFound(
                            response=None,  # type: ignore[arg-type]
                            message="Channel is not a text channel",
                        )

                    message = await channel.fetch_message(application_view["message_id"])
                    await message.edit(view=updated_view)
                except discord.NotFound:
                    logger.exception(
                        "Application channel/message no longer exists (channel_id=%s, message_id=%s, application_id=%s)",
                        application_view["channel_id"],
                        application_view["message_id"],
                        application_id,
                    )
                    await interaction.followup.send(
                        embed=simple_embed(
                            "Application was updated, but its posted message no longer exists.",
                            'cross',
                        ),
                        ephemeral=True,
                    )
                except discord.Forbidden:
                    logger.exception(
                        "Missing permissions to update message_id=%s in channel_id=%s for application_id=%s",
                        application_view["message_id"],
                        application_view["channel_id"],
                        application_id,
                    )
                    await interaction.followup.send(
                        embed=simple_embed(
                            "Application was updated, but I don't have permission to edit its message.",
                            'cross',
                        ),
                        ephemeral=True,
                    )
                except Exception:
                    logger.exception(
                        "Unexpected error editing message_id=%s in channel_id=%s for application_id=%s",
                        application_view["message_id"],
                        application_view["channel_id"],
                        application_id,
                    )
                    await interaction.followup.send(
                        embed=simple_embed("Failed to update the application message.", 'cross'),
                        ephemeral=True,
                    )

            page = self.list_view.page

        try:
            await self.list_view.refresh(interaction, page)
        except Exception:
            logger.exception(
                "Failed to refresh applications list (guild_id=%s, page=%s)",
                guild_id,
                page,
            )
            try:
                await interaction.followup.send(
                    embed=simple_embed(
                        "Saved successfully, but refreshing the list failed. Please reopen the list.",
                        'cross',
                    ),
                    ephemeral=True,
                )
            except Exception:
                logger.exception("Failed to send list refresh failure notice (guild_id=%s)", guild_id)

class RemoveApplicationModal(discord.ui.Modal):
    def __init__(self, list_view: ApplicationsList) -> None:
        super().__init__(title="Remove Application")

        self.list_view = list_view
        self.select = discord.ui.Select(
            placeholder="Select an application",
            options=[
                discord.SelectOption(label=a["name"][:100], value=str(a["id"]))
                for a in list_view.applications
            ],
        )
        self.add_item(discord.ui.Label(text="Application to remove", component=self.select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        application_id = int(self.select.values[0])

        preview = await bot_db.app_management_db.get_delete_preview(interaction.guild.id, application_id)
        if preview is None:
            await self.list_view.refresh(interaction, self.list_view.page)
            return

        name, submission_count = preview
        await interaction.response.edit_message(
            view=ApplicationDeleteConfirm(self.list_view, application_id, name, submission_count)
        )

class ApplicationDeleteConfirm(discord.ui.LayoutView):
    def __init__(self, list_view: ApplicationsList, application_id: int, name: str, submission_count: int) -> None:
        super().__init__(timeout=300)

        self.list_view = list_view
        self.application_id = application_id

        delete_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Delete",
        )
        delete_button.callback = self.delete_callback

        cancel_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Cancel",
        )
        cancel_button.callback = self.cancel_callback

        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                content=(
                    f"### Delete {name}?\n"
                    f"This permanently deletes the application, its **{submission_count}** submission(s) "
                    f"with all answers, and its group assignments. This cannot be undone.\n"
                    f"-# Panel messages and submission threads in Discord are not removed automatically."
                )
            ),
            discord.ui.ActionRow(delete_button, cancel_button),
        ))

    async def delete_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        await bot_db.app_management_db.delete_application(interaction.guild.id, self.application_id)
        await self.list_view.refresh(interaction, self.list_view.page)

    async def cancel_callback(self, interaction: discord.Interaction) -> None:
        await self.list_view.refresh(interaction, self.list_view.page)


class ApplicationQuestionView(discord.ui.LayoutView):
    def __init__(
        self,
        db: BotGlobalsDatabaseAccess,
        question: Dict[str, Any]
    ) -> None:
        super().__init__(timeout=None)

        self.db: BotGlobalsDatabaseAccess = db

        self.question_id: int = question["id"]
        self.guild_id = question["guild_id"]
        self.group_id: int = question["group_id"]
        self.submission_id: int = question["submission_id"]
        self.application_id = question["application_id"]

        label: str = question["label"]
        description: str | None = question["description"]

        question_type: str = question["type"]

        try:
            metadata: Dict[str, Any] = (
                json.loads(question["metadata"])
                if question["metadata"] is not None
                else {}
            )
        except json.JSONDecodeError:
            logger.exception(
                "Failed to parse metadata JSON for question_id=%s in application_id=%s",
                self.question_id,
                self.application_id,
            )
            metadata = {}

        self.additional_component: discord.ui.Select | discord.ui.RadioGroup | None = None

        try:
            if question_type == "selector":
                options = metadata["options"]
                self.additional_component = discord.ui.Select(
                    min_values=1,
                    placeholder="Select an Option...",
                    max_values=1,
                    options=[
                        discord.SelectOption(label=option, value=option)
                        for option in options
                    ]
                )
            elif question_type == "radio_button":
                options = metadata["options"]
                self.additional_component = discord.ui.RadioGroup(
                    options=[
                        discord.RadioGroupOption(label=option, value=option)
                        for option in options
                    ]
                )
        except (KeyError, TypeError):
            logger.exception(
                "Malformed metadata for question_id=%s (type=%s) in application_id=%s: %s",
                self.question_id,
                question_type,
                self.application_id,
                metadata,
            )
            self.additional_component = None

        if self.additional_component is not None:
            self.additional_component.callback = self.additional_components_callback

        self.container = discord.ui.Container(
            discord.ui.TextDisplay(
                content=f"### {label}\n"
                        f"{'- ' + description if description else ''}"
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
        )

        if self.additional_component is not None:
            self.submit_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary,
                    label="Submit"            
            )
            self.submit_button.callback = self.submit_button_callback
            self.container.add_item(
                discord.ui.ActionRow(self.additional_component)
            )

            self.container.add_item(
                discord.ui.ActionRow(
                    self.submit_button
                )
            )

        self.add_item(self.container)

    async def submit_button_callback(self, interaction: discord.Interaction):
        if self.additional_component is None:
            logger.warning(
                "submit_button_callback invoked with no additional_component for question_id=%s",
                self.question_id,
            )
            await interaction.response.send_message(
                "Additional Components is None",
                ephemeral=True,
            )
            return

        if isinstance(self.additional_component, discord.ui.Select):
            value = self.additional_component.values[0]
        elif isinstance(self.additional_component, discord.ui.RadioGroup):
            value = self.additional_component.value
        else:
            logger.warning(
                "Unexpected additional_component type=%s for question_id=%s",
                type(self.additional_component),
                self.question_id,
            )
            return

        if value is None:
            await interaction.response.send_message(
                "Please select an option first.",
                ephemeral=True,
            )
            return

        self.submit_button.disabled = True

        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            logger.exception(
                "Failed to disable submit button on message for question_id=%s",
                self.question_id,
            )

        try:
            await self.db.app_management_db.save_application_answer(
                submission_id=self.submission_id,
                group_id=self.group_id,
                question_id=self.question_id,
                answer_value=value,
            )
        except Exception:
            logger.exception(
                "Failed to save answer for question_id=%s in submission_id=%s",
                self.question_id,
                self.submission_id,
            )
            try:
                await interaction.followup.send(
                    content="Something went wrong saving your answer. Please try again.",
                    ephemeral=True,
                )
            except Exception:
                logger.exception(
                    "Failed to notify user of save failure for question_id=%s in submission_id=%s",
                    self.question_id,
                    self.submission_id,
                )
            return

        try:
            next_question = await self.db.app_management_db.get_unanswered_application_question(
                self.submission_id
            )
        except Exception:
            logger.exception(
                "Failed to fetch next unanswered question for submission_id=%s",
                self.submission_id,
            )
            try:
                await interaction.followup.send(
                    content="Your answer was saved, but I couldn't load the next question. Please try again later.",
                    ephemeral=True,
                )
            except Exception:
                logger.exception(
                    "Failed to notify user of next-question fetch failure for submission_id=%s",
                    self.submission_id,
                )
            return

        if next_question is None:
            try:
                await self.db.app_management_db.update_submission_status(
                    self.submission_id,
                    "completed"
                )
            except Exception:
                logger.exception(
                    "Failed to mark submission_id=%s as completed",
                    self.submission_id,
                )

            try:
                await interaction.followup.send(
                    content="Your application has been submitted successfully. Thank you!"
                )
            except Exception:
                logger.exception(
                    "Failed to send completion message for submission_id=%s",
                    self.submission_id,
                )
            return

        try:
            await interaction.followup.send(
                view=ApplicationQuestionView(
                    self.db,
                    next_question
                )
            )
        except Exception:
            logger.exception(
                "Failed to send next question view for submission_id=%s, next_question_id=%s",
                self.submission_id,
                next_question.get("id") if isinstance(next_question, dict) else None,
            )

    async def additional_components_callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message("Successfully selected. Please press the Submit button once you've confirmed your choice.", ephemeral=True)
        except Exception:
            logger.exception(
                "Failed to send selection confirmation for question_id=%s",
                self.question_id,
            )

class Confirm(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None

    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.secondary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
        except Exception:
            logger.exception("Failed to defer interaction on Confirm button")
        self.value = True
        self.stop()

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            logger.exception("Failed to defer interaction on Cancel button")
        self.value = False
        self.stop()

class ApplicationView(discord.ui.LayoutView):  
    def __init__(
            self,
            db: BotGlobalsDatabaseAccess,
            application_channel_id: int,
            application_id: int, 
            application: Dict[str, Any]
        ) -> None:
        super().__init__(timeout=None)

        self.application = application
        self.application_id = application_id
        self.db: BotGlobalsDatabaseAccess = db

        self.application_name: str = self.application["name"]
        self.submit_btn_label: str = self.application["submit_btn_label"] or "Apply Now"
        self.current_wave: int = self.application["current_wave"]
        self.active: int = self.application["active"]

        self.application_description: str = self.application["description"]
        self.description: List = []

        try:
            description_layout: List[Dict[str, Any]] = json.loads(self.application_description)
            for item in description_layout:
                match item["type"]:
                    case "separator":
                        self.description.append(
                            discord.ui.Separator(
                                visible=True,
                                spacing=discord.SeparatorSpacing.small
                            )
                        )

                    case "img":
                        self.description.append(
                            discord.ui.MediaGallery(
                                discord.MediaGalleryItem(media=item["value"])
                            )
                        )

                    case "text":
                        self.description.append(
                            discord.ui.TextDisplay(content=item["value"])
                        )
        except json.JSONDecodeError:
            logger.debug(
                "application_description for application_id=%s is not JSON layout, treating as plain text",
                self.application_id,
            )
            self.description.append(
                discord.ui.TextDisplay(content=f"{self.application_description}")
            )
        except (KeyError, TypeError):
            logger.exception(
                "Malformed description layout for application_id=%s",
                self.application_id,
            )
            self.description.append(
                discord.ui.TextDisplay(content=f"{self.application_description}")
            )

        self.container = discord.ui.Container(
            discord.ui.TextDisplay(content=f"# {self.application_name} {'(Closed)' if self.active == 0 else ''}"),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            *self.description,
            discord.ui.TextDisplay(content=f"Wave: **{self.current_wave + 1}**"),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        )

        self.submit_button = discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label=self.submit_btn_label,
                    custom_id=f'{application_channel_id}-new-application'               
                )
        
        self.submit_button.callback = self.submit_button_callback

        if self.active == 0:
            self.submit_button.disabled = True
            self.submit_button.label = "Closed"

        self.action_row = discord.ui.ActionRow(
            self.submit_button
        )

        self.container.add_item(self.action_row)
        self.add_item(self.container)

    async def submit_button_callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            logger.warning(
                "ApplicationView.submit_button_callback invoked outside of a guild (user_id=%s)",
                interaction.user.id if interaction.user else None,
            )
            return

        try:
            blocked, reason = await self.db.app_management_db.is_applicant_blocked(
                interaction.guild.id, interaction.user.id
            )
        except Exception:
            logger.exception(
                "Failed to check blocked status for user_id=%s in guild_id=%s",
                interaction.user.id,
                interaction.guild.id,
            )
            await interaction.response.send_message(
                embed=simple_embed("Something went wrong. Please try again later.", 'cross'),
                ephemeral=True,
            )
            return

        if blocked:
            await interaction.response.send_message(
                embed=simple_embed(f"You have been blocked.\nReason: {reason}", 'cross'),
                ephemeral=True,
            )
            return

        try:
            existing = await self.db.app_management_db.get_pending_submission(
                interaction.user.id
            )
        except Exception:
            logger.exception(
                "Failed to fetch pending submission for user_id=%s",
                interaction.user.id,
            )
            await interaction.response.send_message(
                embed=simple_embed("Something went wrong. Please try again later.", 'cross'),
                ephemeral=True,
            )
            return

        if existing is not None:
            await interaction.response.send_message(
                "You already have an application in progress. Please complete it before starting another.",
                ephemeral=True,
            )
            return

        try:
            submission = await self.db.app_management_db.get_submission(
                guild_id=interaction.guild.id,
                application_id=self.application_id,
                member_id=interaction.user.id,
                wave=self.current_wave,
            )
        except Exception:
            logger.exception(
                "Failed to fetch submission for user_id=%s, application_id=%s, wave=%s",
                interaction.user.id,
                self.application_id,
                self.current_wave,
            )
            await interaction.response.send_message(
                embed=simple_embed("Something went wrong. Please try again later.", 'cross'),
                ephemeral=True,
            )
            return

        if submission is not None and submission["status"] in ("submitted", "accepted", "rejected"):
            await interaction.response.send_message(
                "You have already submitted an application for this wave.",
                ephemeral=True,
            )
            return

        view = Confirm()
        try:
            await interaction.response.send_message(
                embed=simple_embed("Are you sure you want to start this application?", 'warn'),
                view=view,
                ephemeral=True,
            )
        except Exception:
            logger.exception(
                "Failed to send confirmation prompt for user_id=%s, application_id=%s",
                interaction.user.id,
                self.application_id,
            )
            return

        await view.wait()

        if view.value is None:
            try:
                await interaction.edit_original_response(
                    embed=simple_embed("Confirmation timed out.", 'cross'),
                    view=None,
                )
            except Exception:
                logger.exception(
                    "Failed to edit response after confirmation timeout for user_id=%s",
                    interaction.user.id,
                )
            return

        if not view.value:
            try:
                await interaction.edit_original_response(
                    embed=simple_embed('Process has been cancelled.', 'cross'),
                    view=None,
                )
            except Exception:
                logger.exception(
                    "Failed to edit response after cancellation for user_id=%s",
                    interaction.user.id,
                )
            return

        if submission is None:
            try:
                submission = await self.db.app_management_db.create_application_submission(
                    guild_id=interaction.guild.id,
                    application_id=self.application_id,
                    member_id=interaction.user.id,
                    wave=self.current_wave,
                )
            except Exception:
                logger.exception(
                    "Failed to create application submission for user_id=%s, application_id=%s",
                    interaction.user.id,
                    self.application_id,
                )
                try:
                    await interaction.edit_original_response(
                        embed=simple_embed("Failed to start your application. Please try again later.", 'cross'),
                        view=None,
                    )
                except Exception:
                    logger.exception(
                        "Failed to notify user of submission creation failure for user_id=%s",
                        interaction.user.id,
                    )
                return

        try:
            question = await self.db.app_management_db.get_unanswered_application_question(
                submission["id"]
            )
        except Exception:
            logger.exception(
                "Failed to fetch first question for submission_id=%s",
                submission["id"],
            )
            try:
                await interaction.edit_original_response(
                    embed=simple_embed("Failed to load the application questions. Please try again later.", 'cross'),
                    view=None,
                )
            except Exception:
                logger.exception(
                    "Failed to notify user of question fetch failure for submission_id=%s",
                    submission["id"],
                )
            return

        if question is None:
            try:
                await interaction.edit_original_response(
                    embed=simple_embed("Your application is already complete."),
                    view=None,
                )
            except Exception:
                logger.exception(
                    "Failed to notify user that submission_id=%s is already complete",
                    submission["id"],
                )
            return

        try:
            await interaction.user.send(
                view=ApplicationQuestionView(self.db, question)
            )
        except discord.Forbidden:
            logger.exception(
                "Could not DM user_id=%s for submission_id=%s (DMs closed)",
                interaction.user.id,
                submission["id"],
            )
            try:
                await interaction.edit_original_response(
                    embed=simple_embed("I couldn't send you a DM. Please enable Direct Messages from server members and try again.", 'cross'),
                    view=None,
                )
            except Exception:
                logger.exception(
                    "Failed to notify user_id=%s that DM could not be sent",
                    interaction.user.id,
                )
            return
        except discord.HTTPException:
            logger.exception(
                "Discord HTTP error while DMing user_id=%s for submission_id=%s",
                interaction.user.id,
                submission["id"],
            )
            try:
                await interaction.edit_original_response(
                    embed=simple_embed("Failed to send the application via DM. Please try again later.", 'cross'),
                    view=None,
                )
            except Exception:
                logger.exception(
                    "Failed to notify user_id=%s of DM HTTP failure",
                    interaction.user.id,
                )
            return

        try:
            await interaction.edit_original_response(
                embed=simple_embed("I've sent you the application in DMs. Please continue it there."),
                view=None,
            )
        except Exception:
            logger.exception(
                "Failed to send final confirmation for user_id=%s, submission_id=%s",
                interaction.user.id,
                submission["id"],
            )