from __future__ import annotations

import discord
from src.core.utils.embeds.sLilyEmbed import simple_embed
from typing import Optional, cast, Any, TYPE_CHECKING, List, Dict, Tuple, Union
from datetime import datetime
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.logging.components.logging_components import ProofsComponentCommandModal
from src.core.features.permissions.lily_permissions import has_app_permission

import src.core.configs.bot_details as Config
import json
import io
from src.core.configs.bot_details import img, emoji
import re

if TYPE_CHECKING:
    from .....lily import Lily

class Leaderboard(discord.ui.LayoutView):
    def __init__(self, bot: discord.Member, leaderboard_type: str, ms_data: list):
        super().__init__(timeout=None)

        self.leaderboard_type = leaderboard_type
        self.ms_data = ms_data

        self.bot = bot

        self.top_ms_staff: int = self.ms_data[0].get("moderator_id")
        self.least_ms_staff: int = self.ms_data[-1].get("moderator_id")

        self.leaderboard_value = ""

        for data in self.ms_data:
            moderator_id: int = data.get("moderator_id")
            ms: int = data.get("ms")

            self.leaderboard_value += f"- **({ms}ms)** <@{moderator_id}>\n"


        self.container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content="## Moderation Statistics Leaderboard"),
                discord.ui.TextDisplay(content=f"- Shows the leaderboard based on,\n  - **(mod_logs)** <@{self.bot.id}>"),
                discord.ui.TextDisplay(content=f"> **Top MS Staff** - <@{self.top_ms_staff}>\n> **Least MS Staff** - <@{self.least_ms_staff}>"),
                accessory=discord.ui.Thumbnail(
                    media=bot.display_avatar.url,
                ),
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content=f"### __{self.leaderboard_type.title()} Leaderboard__"),
            discord.ui.TextDisplay(content=self.leaderboard_value),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            accent_colour=discord.Colour(16777215),
        )

        self.add_item(self.container)

class ModerationInsights(discord.ui.LayoutView):
    def __init__(self, bot: discord.Member, db: BotGlobalsDatabaseAccess):
        super().__init__(timeout=300)

        self.bot = bot
        self.message: Optional[discord.Message] = None
        self.logs_db: BotGlobalsDatabaseAccess = db

        self.ms_leaderboard_options = discord.ui.Select(
            custom_id="ms_leaderboard_options",
            options=[
                discord.SelectOption(label="Daily", value="daily", description="Displays moderation stat leaderboard from the last 24 hours."),
                discord.SelectOption(label="Weekly", value="weekly", description="Displays moderation stat leaderboard for the current week"),
                discord.SelectOption(label="Monthly", value="monthly", description="Displays moderation stat leaderboard for the current month"),
                discord.SelectOption(label="Total", value="total", description="Displays moderation stat leaderboard for the current month"),
            ]
        )

        self.ms_leaderboard_options.callback = self.ms_leaderboard_options_callback

        self.container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content="## Staff Moderation Insights"),
                discord.ui.TextDisplay(content="- Overview of Moderation data that helps the Management Team maintain a safe and well managed staff environment."),
                accessory=discord.ui.Thumbnail(
                    media=self.bot.display_avatar.url,
                ),
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content="### Moderation Statistics Leaderboard"),
            discord.ui.ActionRow(self.ms_leaderboard_options),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content="### Moderation Analysis"),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    media="attachment://moderation_analytics.png",
                ),
            ),
            accent_colour=discord.Colour(16777215),
        )

        self.add_item(self.container)
    
    async def ms_leaderboard_options_callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(embed=simple_embed("Can only be interacted inside an guild", 'cross'), ephemeral=True)
            return 

        if self.logs_db is None:
            await interaction.response.send_message(embed=simple_embed("Internal Failure", 'cross'), ephemeral=True)
            return 
        await interaction.response.defer()

        selected_ms_leaderboard_option = self.ms_leaderboard_options.values[0]
        ms_data_dict: dict = await self.logs_db.fetch_moderation_leaderboard(interaction.guild.id, selected_ms_leaderboard_option)


        ms_data: list = ms_data_dict.get("moderator_statistics_leaderboard", [])
        if not ms_data:
            await interaction.followup.send(embed=simple_embed("No Moderation Data Available", 'cross'))
            return


        view = Leaderboard(self.bot, selected_ms_leaderboard_option, ms_data)
        await interaction.followup.send(view=view, ephemeral=True)

    async def on_timeout(self):
        self.ms_leaderboard_options.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

def action_log(
    action: str,
    reason: Optional[str],
    guild_name: str,
) -> discord.Embed:
    action = action.lower()

    titles = {
        "ban": f"{Config.emoji['arrow']} You Have Been Banned!",
        "mute": f"{Config.emoji['arrow']} You Have Been Muted!",
        "quarantine": f"{Config.emoji['arrow']} You Have Been Quarantined!",
        "warn": f"{Config.emoji['arrow']} You Have Been Warned!",
    }

    if action not in titles:
        raise ValueError(f"Unknown action '{action}'. Must be one of {list(titles)}.")

    embed = discord.Embed(
        color=0xFFFFFF,
        title=titles[action],
    )
    if action == "warn":
        embed.set_thumbnail(url=Config.img['warn'])
    else:
        embed.set_image(url=Config.img.get(action, Config.img['border']))

    embed.add_field(
        name=f"{Config.emoji['bookmark']} Reason",
        value=reason,
        inline=False,
    )
    embed.add_field(
        name=f"{Config.emoji['bot']} Server",
        value=guild_name,
        inline=False,
    )

    return embed

def build_ms_embed(
    moderator: discord.Member | discord.User,
    logs: list[dict],
    stats: dict,
    total_logs: int,
    page_start: int = 0
) -> list[discord.Embed]:

    embed1 = discord.Embed(
        title=f"{Config.emoji['arrow']} {moderator.display_name}'s Moderation Statistics",
        description=(
            f"### Total Stats : **{total_logs}**\n"
            f"- Mutes : **{stats['mute']['total']}**\n"
            f"- Warns: **{stats['warn']['total']}**\n"
            f"- Quarantines: **{stats['quarantine']['total']}**\n"
            f"- Bans: **{stats['ban']['total']}**"
        ),
        colour=16777215
    )

    embed1.set_thumbnail(
        url=moderator.avatar.url if moderator.avatar else Config.img['member']
    )
    embed1.set_image(url=Config.img['border'])

    embed2 = discord.Embed(
        title="Statistics Overview",
        colour=16777215
    )

    embed2.set_image(url=Config.img['border'])

    actions = ["mute", "warn", "ban", "quarantine"]

    for action in actions:
        embed2.add_field(
            name=f"{action.title()} • Today",
            value=stats[action]["today"],
            inline=True
        )
        embed2.add_field(
            name=f"{action.title()} • 7d",
            value=stats[action]["7d"],
            inline=True
        )
        embed2.add_field(
            name=f"{action.title()} • 30d",
            value=stats[action]["30d"],
            inline=True
        )

    logs_text = ""

    for index, log in enumerate(logs, start=page_start + 1):
        ts_unix = int(log["timestamp"])

        logs_text += (
            f"📌 **Log #{index} - {log['mod_type'].title()}**\n"
            f"> {Config.emoji['member']} User: <@{log['target_user_id']}>\n"
            f"> {Config.emoji['bookmark']} Reason: {log['reason']}\n"
            f"> {Config.emoji['clock']} Time: <t:{ts_unix}:R>\n\n"
        )

    embeds = [embed1, embed2]

    if logs_text:
        embed_logs = discord.Embed(
            title=f"{Config.emoji['arrow']} Moderator Action Logs",
            description=logs_text,
            colour=16777215
        ).set_image(
            url="https://media.discordapp.net/attachments/1404797630558765141/1437432525739003904/colorbarWhite.png"
        )

        embeds.append(embed_logs)

    return embeds

class EditCaseModal(discord.ui.Modal):
    def __init__(self,case_id: int, reason: str, _interaction: discord.Interaction) -> None:
        super().__init__(title="Edit Reason")
        self.reason = discord.ui.Label(
            text="Reason",
            description="The description for the case",
            component=discord.ui.TextInput(
                style=discord.TextStyle.short,
                default=reason,
                required=False
            )
        )

        self.add_item(self.reason)
        self.case_id = case_id
        self._interaction = _interaction

    async def on_submit(self, interaction: discord.Interaction) -> None:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        assert isinstance(self.reason.component, discord.ui.TextInput)

        result = await bot_db.edit_case(
            interaction.user.id,
            case_id=self.case_id,
            case_statement=self.reason.component.value,
            absolute=False
        )

        if not result["success"]:
            await interaction.response.send_message(embed=simple_embed(result["message"], 'cross'), ephemeral=True)
            return

        assert interaction.guild is not None
        updated_case_data = await bot_db.get_case(self.case_id)

        if updated_case_data is None:
            await interaction.response.send_message(embed=simple_embed(result["message"]), ephemeral=True)
            return

        new_view = CaseView(self.case_id, updated_case_data)

        if self._interaction.message is not None:
            await self._interaction.edit_original_response(view=new_view)

        await interaction.response.send_message(embed=simple_embed(result["message"]), ephemeral=True)

class CaseView(discord.ui.LayoutView):
    def __init__(self, case_id: int, case_data: Dict[str, Any]) -> None:
        super().__init__(timeout=None)

        self.case_id = case_id
        self.case_data = case_data

        moderator_id = case_data["moderator_id"]
        mod_type = case_data["mod_type"]
        self.reason = case_data["reason"]
        timestamp = case_data["timestamp"]
        self.channel = None

        try:
            dt = datetime.fromisoformat(timestamp)
        except Exception:
            dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        ts_unix = int(dt.timestamp())

        raw_metadata = case_data.get("metadata")
        try:
            metadata: Dict[str, Any] = json.loads(raw_metadata) if raw_metadata else {}
        except (TypeError, json.JSONDecodeError):
            metadata = {}


        if metadata:
            metadata_lines = "\n".join(
                f"> - **{key.title()}**: {value}" for key, value in metadata.items()
            )
        else:
            metadata_lines = "> - *No metadata available*"

        self.edit_case = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["pencil"]
        )

        self.get_proofs = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["paper_clip"]
        )

        self.edit_case.callback = self.edit_case_callback
        self.get_proofs.callback = self.proofs_button_callback

        case_overview = discord.ui.Container(
            discord.ui.TextDisplay(
                content=f"## {emoji['pin']} Case {case_id} | {mod_type.title() if mod_type else '*Unknown*'}"
            ),
            discord.ui.TextDisplay(
                content=(
                    f"> {Config.emoji['staff']} Moderator: <@{moderator_id}>\n"
                    f"> {Config.emoji['clock']} Time: <t:{ts_unix}:f>"
                )
            ),
            discord.ui.Section(
                discord.ui.TextDisplay(content=f"> {Config.emoji['pencil']} Reason: {self.reason}\n"),
                accessory=self.edit_case
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content=f"### Metadata\n{metadata_lines}"),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.Section(
                discord.ui.TextDisplay(content=f"> {Config.emoji['logs']} Proofs\n"),
                accessory=self.get_proofs
            ),
        )
        self.add_item(case_overview)

    async def edit_case_callback(self, interaction: discord.Interaction):
        if has_app_permission(interaction, command_name="case_edit"):
            await interaction.response.send_modal(EditCaseModal(self.case_id, self.reason, interaction))
        else:
            await interaction.response.send_message(embed=simple_embed("Access denied!", 'cross'), ephemeral=True)
            return

    async def proofs_button_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        proofs_references = await bot_db.get_proof_references(interaction.guild.id, case_id=self.case_id)
        if len(proofs_references) <= 0:
            await interaction.response.send_message(
                embed=simple_embed("No Proofs Found for the given case id", 'cross'), ephemeral=True
            )
            return

        logs_channel_id = bot_db.get_channel(interaction.guild.id, "logs_channel")

        await interaction.response.defer(ephemeral=True)

        if not logs_channel_id:
            await interaction.followup.send(
                embed=simple_embed(
                    "Proofs cannot be retrieved: logging channel is not configured.",
                    "cross"
                ),
                ephemeral=True
            )
            return

        if self.channel is None:
            self.channel = interaction.guild.get_channel(logs_channel_id)

            if self.channel is None:
                try:
                    self.channel = await interaction.guild.fetch_channel(logs_channel_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    await interaction.followup.send(
                        embed=simple_embed(
                            "Proofs cannot be retrieved: logging channel is missing or inaccessible.",
                            "cross"
                        ),
                        ephemeral=True
                    )
                    return

        if not isinstance(self.channel, discord.TextChannel):
            return

        files: list[discord.File] = []

        for message_id in proofs_references:
            try:
                message = await self.channel.fetch_message(message_id)
            except discord.NotFound:
                continue
            except discord.Forbidden:
                await interaction.followup.send(
                    embed=simple_embed(
                        "Missing permission to read messages in the logging channel.",
                        "cross"
                    ),
                    ephemeral=True
                )
                return
            except discord.HTTPException:
                continue

            for attachment in message.attachments:
                try:
                    data = await attachment.read()
                    files.append(
                        discord.File(fp=io.BytesIO(data), filename=attachment.filename)
                    )
                except discord.HTTPException:
                    continue

        if not files:
            await interaction.followup.send(
                embed=simple_embed(
                    "No valid proof attachments were found for this case.",
                    "cross"
                ),
                ephemeral=True
            )
            return

        await interaction.followup.send(
            content=f"Proofs for case `{self.case_id}`",
            files=files,
            ephemeral=True
        )  

class CaseListView(discord.ui.LayoutView):
    def __init__(
        self,
        user: Tuple[str, str],
        case_list_data: Dict[str, Any],
        db: BotGlobalsDatabaseAccess,
        *,
        guild_id: int,
        target_user_id: int,
        moderator_id: int | None = None,
        mod_type: str = "all",
    ) -> None:
        super().__init__(timeout=300)

        self.user = user
        self.case_list_data = case_list_data
        self.db = db

        self.guild_id = guild_id
        self.target_user_id = target_user_id
        self.moderator_id = moderator_id
        self.mod_type = mod_type

        self.channel = None

        self.page = case_list_data["page"]
        self.max_page = case_list_data["max_page"]
        self.total_count = case_list_data["total_count"]
        page_logs = case_list_data["results"]

        case_info = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content=f"# {user[0]}'s Case List"),
                discord.ui.TextDisplay(content=f"### Total Logs\n- {self.total_count}"),
                accessory=discord.ui.Thumbnail(
                    media=user[1],
                ),
            ),
        )

        cases: List[discord.ui.Item] = []

        for log in page_logs:
            ts: str = cast(str, log.get("timestamp"))

            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")

            ts_unix = int(dt.timestamp())
            case_id = log.get("case_id")

            info_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=emoji["paper_clip"],
                custom_id=str(case_id),
            )
            info_button.callback = self.case_info_callback

            cases.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=(
                            f"### {emoji["pin"]} Log #{case_id} • {log['mod_type'].title()}\n"
                            f"> {Config.emoji['shield']} Moderator: <@{log['moderator_id']}>\n"
                            f"> {Config.emoji['pencil']} Reason: {log['reason']}\n"
                            f"> {Config.emoji['clock']} Time: <t:{ts_unix}:R>"
                        )
                    ),
                    accessory=info_button,
                )
            )

        case_list = discord.ui.Container(
            discord.ui.TextDisplay(content="# Log's Overview"),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            *cases,
        )

        self.add_item(case_info)
        self.add_item(case_list)
        self.add_item(self.pagination())

    def pagination(self) -> discord.ui.ActionRow:
        row = discord.ui.ActionRow()

        prev_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["left"],
            disabled=not self.case_list_data["has_prev"],
        )
        prev_button.callback = self.previous_button_callback
        row.add_item(prev_button)

        page_indicator: discord.ui.Button = discord.ui.Button(
            label=f"Page {self.page}/{self.max_page}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
        )
        row.add_item(page_indicator)

        next_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["right"],
            disabled=not self.case_list_data["has_next"],
        )
        next_button.callback = self.next_button_callback
        row.add_item(next_button)

        return row

    async def _refresh_page(self, interaction: discord.Interaction, new_page: int) -> None:
        result = await self.db.fetch_mod_logs(
            guild_id=self.guild_id,
            target_user_id=self.target_user_id,
            moderator_id=self.moderator_id,
            mod_type=self.mod_type,
            page=new_page,
        )

        new_view = CaseListView(
            self.user,
            result,
            self.db,
            guild_id=self.guild_id,
            target_user_id=self.target_user_id,
            moderator_id=self.moderator_id,
            mod_type=self.mod_type,
        )
        await interaction.response.edit_message(view=new_view, allowed_mentions=discord.AllowedMentions.none())

    async def previous_button_callback(self, interaction: discord.Interaction) -> None:
        await self._refresh_page(interaction, self.page - 1)

    async def next_button_callback(self, interaction: discord.Interaction) -> None:
        await self._refresh_page(interaction, self.page + 1)

    async def case_info_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        custom_id = interaction.custom_id
        if custom_id is None:
            return

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        case_id = int(custom_id)
        case_data = await bot_db.get_case(case_id)

        if case_data is None:
            await interaction.response.send_message(embed=simple_embed("Case not found", 'cross'), ephemeral=True)
            return

        view = CaseView(case_id, case_data)

        await interaction.response.send_message(view=view, ephemeral=True)

class AppealForumCustomize(discord.ui.Modal):
    name = discord.ui.Label(
            text="Appeal Config",
            description="Appeal config should be in json",
            component=discord.ui.TextInput(
                style = discord.TextStyle.paragraph,
                required=True,
                placeholder="Enter a json config",
                default= """
                    [
                        {
                            "label": "Why should we remove the punishment?",
                            "description": "Explain why the punishment should be removed and how you will follow the rules in future."
                        },
                        {
                            "label": "Why did this happen?",
                            "description": "Explain what caused the punishment and what you will do to prevent it from happening again."
                        }
                    ]
                """
            )
        )
    
    def __init__(self, bot_db: BotGlobalsDatabaseAccess) -> None:
        super().__init__(title="Appeal Forum")

        self.bot_db = bot_db

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        assert isinstance(self.name.component, discord.ui.TextInput)
        await self.bot_db.upsert_appeal_forum(
            interaction.guild.id,
            self.name.component.value
        )

        await interaction.response.send_message(
            embed=simple_embed("Successfully Updated Appeal Forum Config!")
        )

class AppealModal(discord.ui.Modal):
    def __init__(
        self,
        db: BotGlobalsDatabaseAccess,
        case_id: int,
        guild_id: int,
        config: List[Dict[str, Any]],
        _case
    ) -> None:
        super().__init__(
            title="Moderation Appeal",
            timeout=None,
        )

        self.db = db
        self.case_id = case_id
        self.guild_id = guild_id
        self.case = _case

        self.fields: list[tuple[str, discord.ui.TextInput]] = []

        for question in config[:5]:
            text_input = discord.ui.TextInput(
                style=discord.TextStyle.paragraph,
                required=True,
                placeholder="Enter your answer...",
                max_length=2000,
            )

            label = discord.ui.Label(
                text=question["label"],
                description=question.get("description"),
                component=text_input,
            )

            self.fields.append((question["label"], text_input))
            self.add_item(label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = {
            label: text_input.value
            for label, text_input in self.fields
        }

        await interaction.response.defer()
        guild = interaction.client.get_guild(self.guild_id)

        if guild is None:
            try:
                guild = await interaction.client.fetch_guild(self.guild_id)
            except discord.NotFound:
                await interaction.followup.send(
                    embed=simple_embed("Internal Error", 'cross')
                )
                return
            except discord.Forbidden:
                await interaction.followup.send(
                    embed=simple_embed("Internal Error", 'cross')
                )
                return

        appeal_channel_id: int | None = self.db.get_channel(
            self.guild_id,
            "moderation_appeal",
        )

        if appeal_channel_id is None:
            await interaction.followup.send(
                embed=simple_embed("The moderation appeal forum has not been configured.", "cross"),
                ephemeral=True,
            )
            return

        appeal_forum = guild.get_channel(appeal_channel_id)

        if appeal_forum is None:
            try:
                appeal_forum = await guild.fetch_channel(appeal_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                await interaction.followup.send(
                    embed=simple_embed(
                        "The configured moderation appeal forum could not be found.",
                        "cross",
                    ),
                    ephemeral=True,
                )
                return
            
        assert isinstance(appeal_forum, discord.ForumChannel)

        """ Setup an embed """
        appeal_embed = discord.Embed(
            title="Case Appeal",
            description=f"- User: {interaction.user.mention}\n- ID: {interaction.user.id}",
            color=16777215,
        )

        for question, answer in answers.items():
            appeal_embed.add_field(
                name=question,
                value=answer[:1024] or "*No response*",
                inline=False,
            )

        appeal_embed.set_footer(text=f"Case ID: {self.case_id}")
        appeal_embed.set_image(url=img["border"])


        case_info_embed = discord.Embed(
            title="Case Information",
            color=16777215
        )

        case_info_embed.add_field(
            name=f"{emoji["bookmark"]} Case Type",
            value=self.case['mod_type'].title(),
            inline=False
        )

        case_info_embed.add_field(
            name=f"{emoji["pencil"]} Reason",
            value=self.case["reason"] or "No reason Provided",
            inline=False
        )

        case_info_embed.add_field(
            name=f"{emoji["shield"]} Moderator",
            value=f"<@{self.case['moderator_id']}>",
            inline=False
        )

        case_info_embed.set_image(url=img["border"])

        """ Create a thread inside that forum and post all of these"""
        avatar = await interaction.user.display_avatar.to_file(
            filename="avatar.png"
        )

        tag = discord.utils.get(
            appeal_forum.available_tags,
            name="Pending",
        )

        thread, message = await appeal_forum.create_thread(
            name=f"{interaction.user.display_name}'s {self.case['mod_type'].title()} Appeal",
            file=avatar,
            applied_tags=[tag] if tag else [],
            embeds=[appeal_embed, case_info_embed],
            content=f"<@{self.case['moderator_id']}>"
        )

        assert interaction.client.user is not None
        await thread.send(
            content=f"- To reply to the appealer, mention me (<@{interaction.client.user.id}>) and type your message.",
        )

        await self.db.create_appeal(
            self.case_id,
            thread.id
        )

        """ Get Proofs """
        case_proofs = await self.db.get_proof_references(self.guild_id, self.case_id)
        attachments: list[discord.File] = []

        if case_proofs:
            _logging_channel = self.db.get_channel(self.guild_id, "logs_channel")

            if _logging_channel is not None:
                logging_channel = guild.get_channel(int(_logging_channel))

                if logging_channel is None:
                    try:
                        logging_channel = await guild.fetch_channel(int(_logging_channel))
                    except (discord.NotFound, discord.Forbidden):
                        logging_channel = None

                if logging_channel is not None:
                    for message_id in case_proofs:
                        try:
                            assert isinstance(logging_channel, discord.TextChannel)
                            message = await logging_channel.fetch_message(message_id)
                        except (discord.NotFound, discord.Forbidden):
                            continue

                        for attachment in message.attachments:
                            attachments.append(await attachment.to_file())

        if len(case_proofs) > 0:
            await thread.send(
                content=f"### Case Proofs",
                files=attachments
            )

        await interaction.followup.send(
            embed=simple_embed(
                "Your appeal has been submitted successfully. Our staff will review it as soon as possible. Thank you for your patience."
            ),
            ephemeral=True
        )

        await interaction.followup.send(
            content="### You may continue sending messages in this DM if you'd like to provide any additional information.",
            ephemeral=True
        )

class AppealButton(discord.ui.DynamicItem[discord.ui.Button], template=r'button:case:(?P<id>[0-9]+)'):
    def __init__(self, case_id: int | None) -> None:
        super().__init__(
            discord.ui.Button(
                label='Appeal',
                style=discord.ButtonStyle.danger,
                custom_id=f'button:case:{case_id}',
            )
        )
        self.case_id: int | None = case_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Item[Any], match: re.Match[str], /):
        case_id = int(match['id'])
        return cls(case_id)

    async def callback(self, interaction: discord.Interaction) -> None:
        db: Optional[BotGlobalsDatabaseAccess] = cast("Lily", interaction.client).db
        if db is None:
            return
        
        assert self.case_id is not None

        """ Check the validity of the case first """
        _case = await db.get_case(self.case_id)
        if _case is None:
            await interaction.response.send_message(
                embed=simple_embed(
                    "Maybe This case has been already resolved???",
                    "cross",
                ),
                ephemeral=True
            )

            return
        
        """ Check the status of the case """
        appeal_exists = await db.appeal_exists(self.case_id)
        print(appeal_exists)
        if appeal_exists:
            appeal_status = await db.get_appeal_status(self.case_id)
            print(appeal_status)

            if appeal_status == "pending":
                await interaction.response.send_message(
                    embed=simple_embed(
                        "You have already created an appeal for this case.",
                        "cross",
                    ),
                    ephemeral=True,
                )

                return

            elif appeal_status == "accepted":
                await interaction.response.send_message(
                    embed=simple_embed(
                        "This appeal has been accepted.",
                        "cross",
                    ),
                    ephemeral=True,
                )
            
                return

            elif appeal_status in ("denied", "rejected"):
                await interaction.response.send_message(
                    embed=simple_embed(
                        "This appeal has been denied.",
                        "cross",
                    ),
                    ephemeral=True,
                )

                return

        else:
            _config = await db.get_appeal_forum_config(_case["guild_id"])
            await interaction.response.send_modal(AppealModal(
                db,
                self.case_id,
                _case["guild_id"],
                _config,
                _case
            )
        )

class CaseProofsView(discord.ui.View):
    def __init__(self, case_id: int, controller, message: Optional[discord.Message]):
        super().__init__(timeout=300)

        self.case_id = case_id
        self.controller = controller
        self.message = message

    @discord.ui.button(
        label="Attach Proofs",
        style=discord.ButtonStyle.secondary
    )
    async def click_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        assert isinstance(self.message, discord.Message)
        await interaction.response.send_modal(ProofsComponentCommandModal(controller=self.controller, case_id=self.case_id, cmd_view=self, msg=self.message))

class AppealMessageView(discord.ui.LayoutView):
    def __init__(self, message: str, server: str, attachments: List[discord.Attachment]) -> None:
        super().__init__(timeout=None)

        gallery_items = [
            discord.MediaGalleryItem(media=attachment.url)
            for attachment in attachments
        ]

        components: List[
            Union[discord.ui.TextDisplay, discord.ui.MediaGallery, discord.ui.Separator]
        ] = [
            discord.ui.TextDisplay(content=f"### {message}"),
        ]

        if gallery_items:
            components.append(discord.ui.MediaGallery(*gallery_items))

        components.append(
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
        )
        components.append(
            discord.ui.TextDisplay(content=f"-# Message From {server}'s Staff Team")
        )

        self.container1 = discord.ui.Container(*components)
        self.add_item(self.container1)

commands_list: Dict[str, Dict[str, str]] = {
    "ban": {"app_permission": "ban"},
    "quarantine": {"app_permission": "quarantine"},
    "unban": {"app_permission": "unban"},
    "release": {"app_permission": "unban"},
    "mute": {"app_permission": "mute"},
    "warn": {"app_permission": "warn"},
    "unmute": {"app_permission": "unmute"},
    "mod_stats": {"app_permission": "ms"},
    "case_list": {"app_permission": "modlogs"},
    "mod_insights": {"app_permission": "moderation_insights"},
    "case_edit": {"app_permission": "case_edit"},
    "case_edit_absolute": {"app_permission": "case_edit_absolute"},
    "case_delete": {"app_permission": "case_delete"},
    "mod_acronym_add": {"app_permission": "mod_acronym_add"},
    "mod_acronym_remove": {"app_permission": "mod_acronym_remove"},
    "mod_acronym_update": {"app_permission": "mod_acronym_update"},
    "mod_acronyms": {"app_permission": "mod_acronyms"},
    "mod_acronym_transfer": {"app_permission": "mod_acronym_transfer"},
    "appeal_setup": {"app_permission": "mod_appeal_management"},
    "appeal_forum": {"app_permission": "mod_appeal_management"},
    "appeal_accept": {"app_permission": "mod_appeal_handlers"},
    "appeal_reject": {"app_permission": "mod_appeal_handlers"},
}

class PermissionConfigureModal(discord.ui.Modal):
    def __init__(self, command_name: str, app_permission: str, roles: List[int]) -> None:
        super().__init__(title="Permission Configure")

        self.command_name = command_name
        self.app_permission = app_permission
        default_values = []
        for role in roles:
            default_values.append(
                discord.SelectDefaultValue(
                    id=role,
                    type=discord.SelectDefaultValueType.role
                )
            )

        self.allowed_roles = discord.ui.Label(
                text='Allowed Roles',
                description='Select the roles that you want to allow',
                component=discord.ui.RoleSelect(
                    min_values=1,
                    max_values=25,
                    required=True,
                    default_values=default_values
                )
            )

        self.add_item(self.allowed_roles)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        bot = cast("Lily", interaction.client)
        db = bot.db

        assert db is not None
        assert interaction.guild is not None
        assert isinstance(self.allowed_roles, discord.ui.RoleSelect)


        for role in self.allowed_roles.values:
            await db.set_permission(
                interaction.guild.id,
                role.id,
                self.app_permission
            )

        await interaction.response.send_message(
            content=f"Successfully Assigned {self.command_name.replace("_", " ").title()} Permission to {', '.join(role.mention for role in self.allowed_roles.values)}", 
            ephemeral=True
        )

class Confirm(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None

    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.secondary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.value = True
        self.stop()

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.value = False
        self.stop()

""" Moderation Dashboard """
class ModerationDashboard(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        
        self.commands_select = discord.ui.Select(
            options=[
                discord.SelectOption(
                    label=name.replace("_", " ").title()[:45],
                    value=name,
                )
                for name in commands_list
            ],
        )

        self.commands_select.callback = self.commands_select_callback

        self.appeal_handling_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Click to Configure"
        )

        self.appeal_handling_edit_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Edit"
        )

        self.moderation_logging = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            required=True,
            min_values=1,
            placeholder="Choose a channel",
            max_values=1
        )

        self.moderation_logging_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Edit"
        )

        self.appeal_handling_btn.callback = self.appeal_handling_btn_callback
        self.moderation_logging.callback = self.moderation_logging_callback

        container = discord.ui.Container(
            discord.ui.TextDisplay(content="## Lily Moderation Dashboard"),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),

            discord.ui.TextDisplay(content="### Command Permission Systems"),
            discord.ui.ActionRow(
                self.commands_select
            ),

            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),

            discord.ui.TextDisplay(content="### Configure Appeals and Handling"),
            discord.ui.ActionRow(
                self.appeal_handling_btn
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content="### Configure Moderation Logging"),
            discord.ui.ActionRow(
                self.moderation_logging
            ),

        )

        self.add_item(container)

    async def commands_select_callback(self, interaction: discord.Interaction):
        command_name = self.commands_select.values[0]
        app_permission = commands_list[command_name]["app_permission"]

        """ Send the prefilled values """
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        assert interaction.guild is not None

        roles = bot_db.get_permission_roles(interaction.guild.id, app_permission)
        
        await interaction.response.send_modal(PermissionConfigureModal(command_name, app_permission, roles))

    async def appeal_handling_btn_callback(self, interaction: discord.Interaction):
        """ Check appropriate permissions before performing """

        view = Confirm()

        await interaction.response.send_message(
            (
                'This will create the following\n'
                '- **Forums Channel** : A forum channel where the bot would recieve appeals from the member\n'
                '- **Webhook**: A webhook will be created inside the forums channel where it will recieve messages from Users.\n'
                '\n'
                "-# Note: Please allow the bot to do this process on it`s own as It has to setup few things \n"
                'Are you sure you have to proceed with this?'
            ),
            view=view,
            ephemeral=True
        )

        await view.wait()
        
        if view.value is None:
            await interaction.edit_original_response(
                embed=simple_embed("Confirmation timed out.", 'cross'),
                view=None,
            )
            return

        if not view.value:
            await interaction.edit_original_response(
                embed=simple_embed('Process has been cancelled.', 'cross'),
                view=None,
            )
            return

        else:
            pass
            #await setup_mod_appeal(interaction)

    async def moderation_logging_callback(self, interaction: discord.Interaction):
        assert isinstance(self.moderation_logging, discord.ui.ChannelSelect)

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        assert interaction.guild is not None

        await bot_db.set_channel(
            interaction.guild.id,
            self.moderation_logging.values[0].id,
            channel_type="logs_channel"
        )

        await interaction.response.send_message(embed=simple_embed(f"Successfully assigned logging channel to {self.moderation_logging.values[0].mention}"))
