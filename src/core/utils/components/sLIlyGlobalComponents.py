import discord
from discord.utils import MISSING
import src.core.configs.bot_details as Config

from discord.ext import commands
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.utils.embeds.sLilyEmbed import simple_embed



from typing import List, Dict, Any

class CommandInfo(discord.ui.LayoutView):
    def __init__(self, ctx: commands.Context ,cmd_name: str, cmd_usage: List[str]):
        super().__init__()

        self.cmd_name = cmd_name
        self.cmd_usage: List[str] = cmd_usage

        self.formatted_usage: str = "\n".join(f"- {Config.bot_command_prefix}{cmd}" for cmd in self.cmd_usage)
        self.container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content=f"## {self.cmd_name}"),
                discord.ui.TextDisplay(content=f"- {ctx.command.description}"),
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
    def __init__(self, role_id: int ,db: BotGlobalsDatabaseAccess, role_name: str, role_config: Dict[str, Any]) -> None:
        super().__init__(title="Role Configuration")

        self.db = db
        self.role_id = role_id
        self.role_name = role_name

        self.role_type = discord.ui.TextInput(
            label='Role Type',
            style=discord.TextStyle.short,
            placeholder='What kind of role is this',
            required=True,
            max_length=100,
            default=role_config.get("role_type", "staff")
        )

        self.ban_limit = discord.ui.TextInput(
            label='Ban Limit',
            style=discord.TextStyle.short,
            placeholder='Hardcoded Limit that resets 24 hrs',
            required=True,
            max_length=5,
            default=str(role_config.get("ban_limit", "45"))
        )

        _bq_option: int = role_config.get("ban_queue", 0)
        _assign_scope: str = role_config.get("assignment_scope", "none") or "none"

        self.ban_queue_option = discord.ui.Label(
            text='Ban Queue',
            description='Should ban`s undergo a validation before action?',
            component=discord.ui.RadioGroup(
                options=[
                    discord.RadioGroupOption(label="Yes", value="1", description="Their bans require approval through /moderation queue before execution.", default=_bq_option == 1),
                    discord.RadioGroupOption(label="No", value="0", description="Their bans are executed instantly without queue validation.", default=_bq_option != 1)
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
                        default=_assign_scope == "none"
                    ),
                    discord.RadioGroupOption(
                        label="All",
                        value="all",
                        description="This role can assign all available roles.",
                        default=_assign_scope == "all"
                    ),
                    discord.RadioGroupOption(
                        label="Except",
                        value="except",
                        description="This role can assign all roles except selected restricted roles.",
                        default=_assign_scope == "except"
                    ),
                    discord.RadioGroupOption(
                        label="Specified",
                        value="specific",
                        description="This role can only assign specifically selected roles.",
                        default=_assign_scope == "specific"
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
                    discord.Object(id=role_id)
                    for role_id in role_config.get("assignment_roles", [])
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
        assert isinstance(self.role_type, discord.ui.TextInput)



        response = await self.db.configure_role(
            interaction.guild.id,
            self.role_id,
            int(self.ban_limit.value),
            int(self.ban_queue_option.component.value or "0"),
            self.assignment_scope.component.value or "none",
            {role.id for role in (self.assignment_roles.component.values or [])},
            self.role_type.value,
            self.role_name
        )

        if response.get("success"):
            await interaction.followup.send(embed=simple_embed(str(response.get("message"))))
        else:
            await interaction.followup.send(embed=simple_embed(str(response.get("message")), 'cross'))
