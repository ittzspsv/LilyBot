import discord
import logging
from discord.utils import MISSING
import src.core.configs.bot_details as Config
from src.core.configs.bot_details import emoji

from discord.ext import commands
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess, LilyError
from src.core.database.integrations.models import Leaderboard, Role
from src.core.utils.embeds.sLilyEmbed import simple_embed


logger = logging.getLogger("lily")

from typing import List, Optional

class CommandInfo(discord.ui.LayoutView):
    def __init__(self, ctx: commands.Context ,cmd_name: str, cmd_usage: List[str]):
        super().__init__()

        self.cmd_name = cmd_name
        self.cmd_usage: List[str] = cmd_usage
        self.bot_db: BotGlobalsDatabaseAccess = ctx.bot.db

        prefix = self.bot_db.get_prefix_member(ctx.author.id, ctx.guild.id) or self.bot_db.get_prefix(ctx.guild.id) or "."

        description = ctx.command.description if ctx.command else "No description available"

        self.formatted_usage: str = "\n".join(f"- {prefix}{cmd}" for cmd in self.cmd_usage)
        self.container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content=f"## {self.cmd_name}"),
                discord.ui.TextDisplay(content=f"- {description}"),
                discord.ui.TextDisplay(content=f"### Command Usage\n{self.formatted_usage}"),
                accessory=discord.ui.Thumbnail(
                    media=ctx.me.display_avatar.url,
                ),
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        )

        self.add_item(self.container)

class Avatar(discord.ui.LayoutView):
    def __init__(self, member: discord.Member | discord.User) -> None:
        super().__init__(timeout=10)

        self.member = member

        media_gallery = discord.ui.MediaGallery(
            discord.MediaGalleryItem(
                media=member.display_avatar.url,
            ),
        )
        
        action_row = discord.ui.ActionRow(
                discord.ui.Button(
                    url=member.display_avatar.url,
                    style=discord.ButtonStyle.link,
                    label="Download",
                ),
        )

        self.add_item(media_gallery)
        self.add_item(action_row)

class RoleCustomizationModal(discord.ui.Modal):
    def __init__(self, role_id: int ,db: BotGlobalsDatabaseAccess, role_name: str, role_config: Optional[Role]) -> None:
        super().__init__(title="Role Configuration")

        self.db = db
        self.role_id = role_id
        self.role_name = role_name

        # `role_config` is a Role dataclass, or None if the role was never configured.
        current_type: str | None = role_config.role_type if role_config else None
        current_ban_limit: int = (role_config.ban_limit if role_config and role_config.ban_limit is not None else 45)
        current_ban_queue: bool = bool(role_config.ban_queue) if role_config else False
        current_scope: str = (role_config.role_assignment_scope if role_config else "none") or "none"
        current_assignment_roles = role_config.assignment_roles if role_config else frozenset()

        role_options = {
            "staff_base": {
                "name": "Staff Base",
                "description": "Base staff role automatically assigned when using /add staff."
            },
            "staff_loa": {
                "name": "Staff LOA",
                "description": "Role assigned to staff members while they are on leave of absence."
            },
            "staff": {
                "name": "Staff",
                "description": "Staff role included in the rank hierarchy and assigned automatically."
            },
            "higher_staff": {
                "name": "Higher Staff",
                "description": "Role assigned to staff members holding a higher staff position."
            },
            "quarantine": {
                "name": "Quarantine",
                "description": "Role assigned to members who are placed under quarantine."
            }
        }

        self.role_type = discord.ui.Label(
            text="Role Type",
            description="Select the type of role you want to configure.",
            component=discord.ui.Select(
                min_values=1,
                max_values=1,
                required=True,
                options=[
                    discord.SelectOption(
                        label=option["name"],
                        value=option_type,
                        description=option["description"],
                        default=current_type == option_type
                    )
                    for option_type, option in role_options.items()
                ]
            )
        )

        self.ban_limit = discord.ui.TextInput(
            label='Ban Limit',
            style=discord.TextStyle.short,
            placeholder='Hardcoded Limit that resets 24 hrs',
            required=True,
            max_length=5,
            default=str(current_ban_limit)
        )

        self.ban_queue_option = discord.ui.Label(
            text='Ban Queue',
            description='Should ban`s undergo a validation before action?',
            component=discord.ui.RadioGroup(
                options=[
                    discord.RadioGroupOption(label="Yes", value="1", description="Their bans require approval through /moderation queue before execution.", default=current_ban_queue),
                    discord.RadioGroupOption(label="No", value="0", description="Their bans are executed instantly without queue validation.", default=not current_ban_queue)
                ],
            )
        )

        self.assignment_scope = discord.ui.Label(
            text='Role Assignment Scope',
            description='Choose how broadly this role can assign roles',
            component=discord.ui.RadioGroup(
                options=[
                    discord.RadioGroupOption(
                        label="None",
                        value="none",
                        description="This role cannot assign any roles.",
                        default=current_scope == "none"
                    ),
                    discord.RadioGroupOption(
                        label="All",
                        value="all",
                        description="This role can assign all available roles.",
                        default=current_scope == "all"
                    ),
                    discord.RadioGroupOption(
                        label="Except",
                        value="except",
                        description="This role can assign all roles except selected restricted roles.",
                        default=current_scope == "except"
                    ),
                    discord.RadioGroupOption(
                        label="Specified",
                        value="specific",
                        description="This role can only assign specifically selected roles.",
                        default=current_scope == "specific"
                    ),
                ]
            )
        )

        self.assignment_roles = discord.ui.Label(
            text='Role Assignments',
            description='Select roles allowed under the chosen assignment scope',
            component=discord.ui.RoleSelect(
                min_values=1,
                max_values=25,
                required=False,
                default_values=[
                    discord.Object(id=assigned_id)
                    for assigned_id in current_assignment_roles
                ]
            )
        )

        self.add_item(self.role_type)
        self.add_item(self.ban_limit)
        self.add_item(self.ban_queue_option)
        self.add_item(self.assignment_roles)
        self.add_item(self.assignment_scope)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        
        await interaction.response.defer()

        assert isinstance(self.ban_limit, discord.ui.TextInput)
        assert isinstance(self.ban_queue_option.component, discord.ui.RadioGroup)
        assert isinstance(self.assignment_scope.component, discord.ui.RadioGroup)
        assert isinstance(self.assignment_roles.component, discord.ui.RoleSelect)
        assert isinstance(self.role_type.component, discord.ui.Select)

        try:
            ban_limit = int(self.ban_limit.value)
        except ValueError:
            await interaction.followup.send(embed=simple_embed("Ban limit must be a whole number.", 'cross'))
            return

        try:
            # configure_role now returns the saved Role and raises on failure.
            role = await self.db.configure_role(
                interaction.guild.id,
                self.role_id,
                ban_limit,
                int(self.ban_queue_option.component.value or "0"),
                self.assignment_scope.component.value or "none",
                {assigned.id for assigned in (self.assignment_roles.component.values or [])},
                self.role_type.component.values[0],
            )
        except LilyError as e:
            await interaction.followup.send(embed=simple_embed(str(e), 'cross'))
            return
        except Exception:
            logger.exception(
                "RoleCustomizationModal.on_submit: configure_role failed for role %s in guild %s",
                self.role_id, interaction.guild.id
            )
            await interaction.followup.send(embed=simple_embed("Failed to configure the role due to an unexpected error!", 'cross'))
            return

        await interaction.followup.send(
            embed=simple_embed(
                f"Successfully configured {role.mention} as `{role.role_type}` "
                f"(ban limit: {role.ban_limit}, scope: `{role.role_assignment_scope}`)."
            )
        )

class LeaderboardView(discord.ui.LayoutView):
    def __init__(
        self,
        guild_name: str,
        leaderboard_data: Leaderboard,
        db: BotGlobalsDatabaseAccess,
        *,
        guild_id: int,
        leaderboard_type: int,
        requester_id: int,
        leaderboard_img_available: bool = False
    ) -> None:
        super().__init__(timeout=None)

        self.guild_name = guild_name
        self.leaderboard_data = leaderboard_data
        self.db = db
        self.leaderboard_img_available = leaderboard_img_available

        self.guild_id = guild_id
        self.leaderboard_type = leaderboard_type
        self.requester_id = requester_id

        self.message: discord.Message | None = None

        # Leaderboard(type, page: Page[LeaderboardEntry], target: LeaderboardEntry | None)
        self.page = leaderboard_data.page.page
        self.total_pages = leaderboard_data.page.max_page
        self.total_count = leaderboard_data.page.total_count
        entries = leaderboard_data.page.items
        target_entry = leaderboard_data.target

        type_label = leaderboard_data.type.title()

        rows: List[discord.ui.Item] = []

        for entry in entries:
            rows.append(
                discord.ui.TextDisplay(
                    content=(
                        f"{entry.rank}. <@{entry.member_id}> — "
                        f"**{entry.count:,}** messages"
                    )
                )
            )

        board = discord.ui.Container(
            discord.ui.TextDisplay(content=f"# {type_label} Leaderboard"),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
        )

        if self.leaderboard_img_available:
            board.add_item(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(
                            media="attachment://leaderboard.png",
                        ),
                    )
            )

            board.add_item(
                discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
            )
        for row in rows:
            board.add_item(
                row
            )

        board.add_item(
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
        )

        if target_entry is not None:
            board.add_item(
                discord.ui.TextDisplay(
                    content=(
                        f"Your rank: **#{target_entry.rank}** "
                        f"— {target_entry.count:,} messages"
                    )
                )
            )

        self.add_item(board)

        self.add_item(self.pagination())

    def pagination(self) -> discord.ui.ActionRow:
        row = discord.ui.ActionRow()

        prev_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["left"],
            disabled=self.page <= 1,
        )
        prev_button.callback = self.previous_button_callback
        row.add_item(prev_button)

        page_indicator: discord.ui.Button = discord.ui.Button(
            label=f"Page {self.page}/{self.total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
        )
        row.add_item(page_indicator)

        next_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["right"],
            disabled=self.page >= self.total_pages,
        )
        next_button.callback = self.next_button_callback
        row.add_item(next_button)

        return row

    async def _refresh_page(self, interaction: discord.Interaction, new_page: int) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                embed=simple_embed("You can't control someone else's leaderboard view.", 'cross'),
                ephemeral=True,
            )
            return

        try:
            result = await self.db.leaderboard(
                self.guild_id,
                self.leaderboard_type,
                self.requester_id,
                page=new_page,
            )

            new_view = LeaderboardView(
                self.guild_name,
                result,
                self.db,
                guild_id=self.guild_id,
                leaderboard_type=self.leaderboard_type,
                requester_id=self.requester_id,
                leaderboard_img_available=self.leaderboard_img_available
            )
            new_view.message = self.message
            await interaction.response.edit_message(view=new_view, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            logger.exception(
                "Failed to refresh leaderboard page=%s for guild_id=%s type=%s",
                new_page,
                self.guild_id,
                self.leaderboard_type,
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=simple_embed("Something went wrong while changing pages.", 'cross'), ephemeral=True)
            else:
                await interaction.followup.send(embed=simple_embed("Something went wrong while changing pages.", 'cross'), ephemeral=True)

    async def refresh(self) -> None:
        if self.message is None:
            logger.warning("LeaderboardView.refresh called with no stored message (guild_id=%s)", self.guild_id)
            return

        try:
            result = await self.db.leaderboard(
                self.guild_id,
                self.leaderboard_type,
                self.requester_id,
                page=self.page,
            )

            new_view = LeaderboardView(
                self.guild_name,
                result,
                self.db,
                guild_id=self.guild_id,
                leaderboard_type=self.leaderboard_type,
                requester_id=self.requester_id,
                leaderboard_img_available=self.leaderboard_img_available
            )
            new_view.message = self.message

            await self.message.edit(view=new_view, allowed_mentions=discord.AllowedMentions.none())
        except (discord.NotFound, discord.HTTPException):
            logger.exception(
                "Failed to refresh leaderboard (guild_id=%s type=%s) — message likely expired",
                self.guild_id,
                self.leaderboard_type,
            )

    async def previous_button_callback(self, interaction: discord.Interaction) -> None:
        await self._refresh_page(interaction, self.page - 1)

    async def next_button_callback(self, interaction: discord.Interaction) -> None:
        await self._refresh_page(interaction, self.page + 1)