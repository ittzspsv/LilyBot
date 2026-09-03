import discord
import json
import logging

from typing import Dict, Any, List

from ....database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.utils.embeds.sLilyEmbed import simple_embed

logger = logging.getLogger("lily")


class CreateApplicationModal(discord.ui.Modal, title="Create Application"):
    def __init__(self, bot_db: BotGlobalsDatabaseAccess, application_groups: List[Dict[str, Any]]) -> None:
        super().__init__()
        self.bot_db: BotGlobalsDatabaseAccess = bot_db

        self.name = discord.ui.Label(
            text="Application Name",
            description="Enter the application name",
            component=discord.ui.TextInput(
                style = discord.TextStyle.short,
                min_length=1,
                max_length=45,
                required=True,
                placeholder="Staff Application"
            )
        )

        self.description = discord.ui.Label(
            text="Application Description",
            description="Enter the description of application",
            component=discord.ui.TextInput(
                style = discord.TextStyle.paragraph,
                min_length=1,
                max_length=1024,
                required=True,
                placeholder="Sample staff application"
            )
        )

        app_group_options: List[discord.SelectOption] = []
        for group in application_groups:
            id = group["id"]
            name = group["name"]
            description = group["description"]

            app_group_options.append(
                discord.SelectOption(
                    label=name[:45],
                    value=str(id),
                    description=description[:100]
                )
            )

        self.app_groups = discord.ui.Label(
            text="Application Groups",
            description="Select the group of questions for your application",
            component=discord.ui.Select(
                min_values=1,
                max_values=max(1, len(app_group_options)),
                options=app_group_options
            )   
        )

        self.submit_btn_name = discord.ui.Label(
            text="Submit button label",
            description="Enter the label that will appear on the application's submit button.",
            component=discord.ui.TextInput(
                style = discord.TextStyle.short,
                min_length=1,
                max_length=45,
                required=True,
                default="Apply Now"
            )
        )

        self.add_item(self.name)
        self.add_item(self.description)
        self.add_item(self.app_groups)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            logger.warning(
                "CreateApplicationModal.on_submit called outside of a guild (user_id=%s)",
                interaction.user.id if interaction.user else None,
            )
            raise discord.app_commands.CheckFailure("This command can be only executed inside an guild")

        await interaction.response.defer()
        assert isinstance(self.name.component, discord.ui.TextInput)
        assert isinstance(self.description.component, discord.ui.TextInput)
        assert isinstance(self.app_groups.component, discord.ui.Select)
        assert isinstance(self.submit_btn_name.component, discord.ui.TextInput)

        try:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(
                    view_channel=False
                ),

                interaction.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    manage_channels=True,
                    manage_threads=True,
                    send_messages=True,
                    create_public_threads=True,
                ),

                interaction.user: discord.PermissionOverwrite(
                    view_channel=True,
                    manage_permissions=True,
                    manage_channels=True,
                    send_messages=True,
                    read_message_history=True,
                    create_public_threads=True,
                    create_private_threads=True,
                    send_messages_in_threads=True,
                    attach_files=True,
                    embed_links=True,
                    add_reactions=True,
                    use_external_emojis=True,
                    use_external_stickers=True,
                    mention_everyone=False,
                ),
            }
            forum = await interaction.guild.create_forum(
                name=f"{self.name.component.value}-submissions",
                available_tags=[
                    discord.ForumTag(name="Pending", emoji="⏳"),
                    discord.ForumTag(name="Accepted", emoji="✅"),
                    discord.ForumTag(name="In Review", emoji="📋"),
                    discord.ForumTag(name="Denied", emoji="❌"),
                ],
                overwrites=overwrites,
            )

        except discord.Forbidden:
            logger.exception(
                "Missing permissions to create submission forum in guild_id=%s",
                interaction.guild.id,
            )
            raise discord.app_commands.CheckFailure("I don't have permissions creating text channels.")
        except discord.HTTPException:
            logger.exception(
                "Discord HTTP error while creating submission forum in guild_id=%s",
                interaction.guild.id,
            )
            raise discord.app_commands.CheckFailure("Failed to create submission forms due to a Discord API error.")
        except Exception as e:
            logger.exception(
                "Unexpected error while creating submission forum in guild_id=%s",
                interaction.guild.id,
            )
            raise discord.app_commands.CheckFailure(f"Failed to create submission forms: {e}")

        try:
            selected_group_ids = [int(value) for value in self.app_groups.component.values]
        except (TypeError, ValueError):
            logger.exception(
                "Failed to parse selected application group ids: %s",
                self.app_groups.component.values,
            )
            await interaction.followup.send(
                embed=simple_embed("Invalid application group selection.", 'cross')
            )
            return

        try:
            application = await self.bot_db.app_management_db.create_application(
                interaction.guild.id,
                self.name.component.value,
                self.description.component.value,
                forum.id,
                self.submit_btn_name.component.value
            )
        except Exception:
            logger.exception(
                "Failed to create application record in database for guild_id=%s",
                interaction.guild.id,
            )
            await interaction.followup.send(
                embed=simple_embed("Failed to save the application. Please try again later.", 'cross')
            )
            return

        try:
            await self.bot_db.app_management_db.assign_groups(
                interaction.guild.id,
                application["id"],
                selected_group_ids
            )
        except Exception:
            logger.exception(
                "Failed to assign groups %s to application_id=%s in guild_id=%s",
                selected_group_ids,
                application["id"],
                interaction.guild.id,
            )
            await interaction.followup.send(
                embed=simple_embed("Application was created, but assigning question groups failed.", 'cross')
            )
            return

        try:
            await interaction.followup.send(
                embed=discord.Embed(
                    color=16777215,
                    title=f"Successfully Created an Application with name **{self.name.component.value}**",
                    description=(
                        f"- Created a submission forum: <#{forum.id}>.\n"
                        "- Tags:\n"
                        "  - Pending (don't rename or delete)\n"
                        "  - Accepted\n"
                        "  - Denied\n",
                        "  - In Review\n"
                        "- You can add more tags as needed.\n"
                        "- **Pending** is used internally to auto-assign application submissions."
                    ),
                )
            )
        except Exception:
            logger.exception(
                "Failed to send success confirmation for application_id=%s in guild_id=%s",
                application["id"],
                interaction.guild.id,
            )

class UpdateApplicationModal(discord.ui.Modal, title="Update Application"):
    def __init__(self, bot_db: BotGlobalsDatabaseAccess, application: Dict[str, Any]) -> None:
        super().__init__()
        self.bot_db: BotGlobalsDatabaseAccess = bot_db
        self.application = application

        self.name = discord.ui.Label(
            text="Application Name",
            description="Enter the application name",
            component=discord.ui.TextInput(
                style = discord.TextStyle.short,
                min_length=1,
                max_length=45,
                required=True,
                placeholder="Staff Application",
                default=application["name"]
            )
        )

        self.description = discord.ui.Label(
            text="Application Description",
            description="Enter the description of application",
            component=discord.ui.TextInput(
                style = discord.TextStyle.paragraph,
                min_length=1,
                max_length=1024,
                required=True,
                placeholder="Sample staff application",
                default=application["description"]
            )
        )

        self.submit_btn_name = discord.ui.Label(
            text="Submit button label",
            description="Enter the label that will appear on the application's submit button.",
            component=discord.ui.TextInput(
                style = discord.TextStyle.short,
                min_length=1,
                max_length=45,
                required=True,
                default=application["submit_btn_label"] or "Apply Now"
            )
        )

        self.add_item(self.name)
        self.add_item(self.description)
        self.add_item(self.submit_btn_name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            logger.warning(
                "UpdateApplicationModal.on_submit called outside of a guild (user_id=%s)",
                interaction.user.id if interaction.user else None,
            )
            raise discord.app_commands.CheckFailure("This command can be only executed inside an guild")

        await interaction.response.defer()
        assert isinstance(self.name.component, discord.ui.TextInput)
        assert isinstance(self.description.component, discord.ui.TextInput)
        assert isinstance(self.submit_btn_name.component, discord.ui.TextInput)

        try:
            success = await self.bot_db.app_management_db.update_application(
                interaction.guild.id,
                self.application["id"],
                self.name.component.value,
                self.description.component.value,
                self.submit_btn_name.component.value
            )
        except Exception:
            logger.exception(
                "Failed to update application_id=%s in guild_id=%s",
                self.application["id"],
                interaction.guild.id,
            )
            await interaction.followup.send(embed=simple_embed("Failed to update Application", 'cross'))
            return

        if success:
            """ Update the application view """
            try:
                application_view = await self.bot_db.app_management_db.get_application_with_view(
                    interaction.guild.id,
                    self.application["id"]
                )
                assert application_view is not None

                application = await self.bot_db.app_management_db.get_application(
                    interaction.guild.id,
                    self.application["id"]
                )

                assert application is not None
            except Exception:
                logger.exception(
                    "Failed to fetch application/view data for application_id=%s in guild_id=%s after update",
                    self.application["id"],
                    interaction.guild.id,
                )
                await interaction.followup.send(
                    embed=simple_embed(
                        "Application was updated, but refreshing the application message failed.",
                        'cross',
                    )
                )
                return

            updated_view = ApplicationView(
                self.bot_db,
                application_view["channel_id"],
                application["id"],
                application
            )

            try:
                channel = interaction.guild.get_channel(application_view["channel_id"])
                if not isinstance(channel, discord.TextChannel):
                    channel = await interaction.guild.fetch_channel(application_view["channel_id"])
            except discord.NotFound:
                logger.exception(
                    "Application channel_id=%s no longer exists for application_id=%s in guild_id=%s",
                    application_view["channel_id"],
                    self.application["id"],
                    interaction.guild.id,
                )
                await interaction.followup.send(embed=simple_embed("Application channel no longer exists.", 'cross'))
                return
            except discord.Forbidden:
                logger.exception(
                    "Missing permissions to fetch channel_id=%s for application_id=%s in guild_id=%s",
                    application_view["channel_id"],
                    self.application["id"],
                    interaction.guild.id,
                )
                await interaction.followup.send(
                    embed=simple_embed("I don't have permission to access the application channel.", 'cross')
                )
                return
            except Exception:
                logger.exception(
                    "Unexpected error fetching channel_id=%s for application_id=%s in guild_id=%s",
                    application_view["channel_id"],
                    self.application["id"],
                    interaction.guild.id,
                )
                await interaction.followup.send(
                    embed=simple_embed("Failed to access the application channel.", 'cross')
                )
                return

            if not isinstance(channel, discord.TextChannel):
                logger.warning(
                    "Resolved channel_id=%s for application_id=%s in guild_id=%s is not a TextChannel (type=%s)",
                    application_view["channel_id"],
                    self.application["id"],
                    interaction.guild.id,
                    type(channel),
                )
                await interaction.followup.send(embed=simple_embed("Application channel no longer exists.", 'cross'))
                return

            try:
                message = await channel.fetch_message(application_view["message_id"])
                await message.edit(view=updated_view)
            except discord.NotFound:
                logger.exception(
                    "Application message_id=%s no longer exists in channel_id=%s for application_id=%s",
                    application_view["message_id"],
                    channel.id,
                    self.application["id"],
                )
                await interaction.followup.send(embed=simple_embed("The application message no longer exists.", 'cross'))
                return
            except discord.Forbidden:
                logger.exception(
                    "Missing permissions to edit message_id=%s in channel_id=%s for application_id=%s",
                    application_view["message_id"],
                    channel.id,
                    self.application["id"],
                )
                await interaction.followup.send(
                    embed=simple_embed("I don't have permission to update the application message.", 'cross')
                )
                return
            except Exception:
                logger.exception(
                    "Unexpected error editing message_id=%s in channel_id=%s for application_id=%s",
                    application_view["message_id"],
                    channel.id,
                    self.application["id"],
                )
                await interaction.followup.send(
                    embed=simple_embed("Failed to update the application message.", 'cross')
                )
                return

            try:
                await interaction.followup.send(embed=simple_embed(f"Successfully updated {self.name.component.value}"))
            except Exception:
                logger.exception(
                    "Failed to send update confirmation for application_id=%s in guild_id=%s",
                    self.application["id"],
                    interaction.guild.id,
                )
        else:
            logger.warning(
                "update_application returned falsy success for application_id=%s in guild_id=%s",
                self.application["id"],
                interaction.guild.id,
            )
            try:
                await interaction.followup.send(embed=simple_embed("Failed to update Application", 'cross'))
            except Exception:
                logger.exception(
                    "Failed to send failure notice for application_id=%s in guild_id=%s",
                    self.application["id"],
                    interaction.guild.id,
                )

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
            blocked = await self.db.app_management_db.is_applicant_blocked(
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
                embed=simple_embed("You have been blocked.", 'cross'),
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