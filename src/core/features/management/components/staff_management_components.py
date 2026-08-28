import discord
import src.core.configs.sBotDetails as Configs

from typing import Dict, Optional
from discord.ext import commands
from src.core.utils.embeds.sLilyEmbed import simple_embed
from ..embeds.staff_management_embed import loa_accept_embed, loa_reject_embed, infraction_embed
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess

from typing import List, Any

class StaffListView(discord.ui.LayoutView):
    def __init__(self, interaction: discord.Interaction, role_data: dict, role_id: int, page: int = 0, per_page: int = 6):
        super().__init__()

        self.owner_id = interaction.user.id
        self.role_data = role_data
        self.role_id = role_id
        self.per_page = per_page

        staffs_complete = role_data.get("staff", [])
        self.total_staff = len(staffs_complete)

        max_page = max((self.total_staff - 1) // per_page, 0)
        self.page = max(0, min(page, max_page))

        start = self.page * per_page
        end = start + per_page
        staffs = staffs_complete[start:end]

        assert isinstance(interaction.guild, discord.Guild)

        role = interaction.guild.get_role(role_id)
        role_icon_url = role.icon.url if role and role.icon else interaction.guild.me.display_avatar.url

        staff_sections = []

        for i, staff in enumerate(staffs):
            avatar = staff.get('avatar_profile') or interaction.guild.me.display_avatar.url

            staff_sections.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=(
                            f"### <@{staff.get('id','Unknown')}>\n"
                            f"- Timezone : {staff.get('timezone','Default')}\n"
                            f"- Joined : <t:{staff.get('joined_on')}:R>"
                        )
                    ),
                    accessory=discord.ui.Thumbnail(media=avatar)
                )
            )

            if i < len(staffs) - 1:
                staff_sections.append(
                    discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
                )

        role_section = discord.ui.Section(
            discord.ui.TextDisplay(
                content=f"## {role_data.get('role_name','Unknown')}\n"
                        f"- Total Staff: `{self.total_staff}`\n"
                        f"- Page: `{self.page+1}/{max_page+1}`"
            ),
            accessory=discord.ui.Thumbnail(media=role_icon_url)
        )

        container_items = [
            role_section,
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            *staff_sections
        ]

        buttons = discord.ui.ActionRow()

        if self.page > 0:
            left = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="⏪")
            left.callback = self.left_paginator_callback
            buttons.add_item(left)

        if end < self.total_staff:
            right = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="⏩")
            right.callback = self.right_paginator_callback
            buttons.add_item(right)

        if buttons.children:
            container_items.append(buttons)

        container_items.append(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=Configs.img['border'])
            )
        )

        self.container = discord.ui.Container(*container_items)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only instigator has authority to access.",
                ephemeral=True
            )
            return False
        return True

    async def left_paginator_callback(self, interaction: discord.Interaction):
        view = StaffListView(
            interaction,
            self.role_data,
            self.role_id,
            page=self.page - 1
        )
        await interaction.response.edit_message(view=view)

    async def right_paginator_callback(self, interaction: discord.Interaction):
        view = StaffListView(
            interaction,
            self.role_data,
            self.role_id,
            page=self.page + 1
        )
        await interaction.response.edit_message(view=view)

class LOAStaffsView(discord.ui.LayoutView):
    def __init__(self, interaction: discord.Interaction ,staff_datas: List[Dict[str, Any]]):
        super().__init__()

        self.staff_datas = staff_datas
        self.interaction = interaction
        self.staff_ids = ""

        for staff_data in staff_datas:
            self.staff_ids += f'<@{staff_data.get("staff_id")}>\n'

        if not self.staff_ids:
            self.staff_ids = "No Staffs Returned"

        self.container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content="## LOA Staffs"),
                discord.ui.TextDisplay(content="- List all the staffs who are on leave"),
                accessory=discord.ui.Thumbnail(
                media = (
                    self.interaction.guild.icon.url
                    if self.interaction.guild.icon
                    else self.interaction.client.user.avatar.url
                    )                
                ),
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content=self.staff_ids),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        )

        self.add_item(self.container)

class StaffsView(discord.ui.LayoutView):
    def __init__(self, interaction: discord.Interaction, db: BotGlobalsDatabaseAccess ,overall_details: Dict, role_users_map):
        super().__init__(timeout=500)

        self.message: Optional[discord.Message] = None
        self.db: BotGlobalsDatabaseAccess = db
        self.role_users_map = role_users_map

        role_select_options = [
            discord.SelectOption(
                label=data["role_name"],
                value=str(role_id),
            )
            for role_id, data in sorted(
                role_users_map.items(),
                key=lambda item: item[1]["priority"],
            )
            if data["role_type"] == "staff"
        ]

        self.roles_selector = discord.ui.Select(
            custom_id="roles_selector",
            options=role_select_options,
            placeholder="Select a staff role..."
        )

        self.loa_staffs_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="List LOA Staffs",
            )


        self.roles_selector.callback = self.role_selector_callback
        self.loa_staffs_btn.callback = self.loa_staffs_callback

        assert isinstance(interaction.guild, discord.Guild)

        self.container_1 = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(
                    content=(
                        "## Staff's Overview\n"
                        "- Lily's Staff Management System.\n\n"
                    )
                ),
                accessory=discord.ui.Thumbnail(media=interaction.guild.icon.url)
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content="### Server Staff Team\n- List of Role Category who has **Moderation/Administration/Management** Authority"),
            discord.ui.TextDisplay(content=f"### __Overall Details__\n"
                        f"- **ON LOA** - `{overall_details.get("staff").get('loa')}`\n"
                        f"- **Active Staffs** - `{overall_details.get("staff").get('active')}`\n"
                        f"- **Total Staffs** - `{overall_details.get("staff").get('total')}`"),
            discord.ui.ActionRow(self.roles_selector),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.Section(
                    discord.ui.TextDisplay(content="### LOA Staffs"),
                    discord.ui.TextDisplay(content="- Displays All Staffs who are on leave"),
                    accessory=self.loa_staffs_btn
                ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            accent_colour=discord.Colour(16777215),
        )

        self.add_item(self.container_1)

    async def role_selector_callback(self, interaction: discord.Interaction):
        selected_role_id = int(self.roles_selector.values[0])
        role_data = self.role_users_map[selected_role_id]

        view = StaffListView(interaction, role_data, selected_role_id)

        await interaction.response.send_message(
            view=view,
            ephemeral=True
        )

    async def loa_staffs_callback(self, interaction: discord.Interaction):
        assert isinstance(interaction.guild, discord.Guild)
        staff_datas: List[Dict[str, Any]] = await self.db.fetch_loa_staffs(interaction.guild.id, "staff")
        view = LOAStaffsView(interaction, staff_datas)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def on_timeout(self):
        self.roles_selector.disabled = True
        self.loa_staffs_btn.disabled = True
        if self.message is None:
            return
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass

class LOARequestView(discord.ui.LayoutView):
    def __init__(self, bot_db: BotGlobalsDatabaseAccess, staff_id: int, guild_id: int ,staff_pfp: str ,reason: str, days: str) -> None:
        super().__init__(timeout=None)

        self.staff_id = staff_id
        self.reason = reason
        self.days = days
        self.bot_db = bot_db

        self.accept_button = discord.ui.Button(
                                style=discord.ButtonStyle.primary,
                                label="Accept",
                                custom_id=f"loa-accept{staff_id}{guild_id}",
                            )
        
        self.reject_button = discord.ui.Button(
                                style=discord.ButtonStyle.danger,
                                label="Reject",
                                custom_id=f"loa-reject{staff_id}{guild_id}"
                            )
        
        self.accept_button.callback = self.accept_button_callback
        self.reject_button.callback = self.reject_button_callback
        self.status_display = discord.ui.TextDisplay(content="Status: Pending")

        self.container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content=f"### LOA Request | <@{self.staff_id}>"),
                discord.ui.TextDisplay(content=f"Reason: **{self.reason}**"),
                discord.ui.TextDisplay(content=f"Days: **{self.days}**"),
                accessory=discord.ui.Thumbnail(
                    media=staff_pfp,
                ),
            ),
            self.status_display,
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.ActionRow(
                    self.accept_button,
                    self.reject_button
            ),
        )

        self.add_item(self.container)

    async def accept_button_callback(self, interaction: discord.Interaction):
        assert isinstance(interaction.guild, discord.Guild)

        if self.staff_id ==  interaction.user.id:
            return await interaction.response.send_message(embed=simple_embed("You cannot accept your LOA", 'cross'), ephemeral=True)
 

        await interaction.response.defer()

        result = await self.bot_db.add_loa(
            interaction.guild.id,
            self.staff_id,
            self.reason,
            interaction.user.id
        )

        if result.get("success"):
            """ Removing the pending from LOA """
            await self.bot_db.delete_loa_pending(self.staff_id, interaction.guild.id)


            roles_to_remove = set(result.get("roles_to_remove", ()))
            roles_to_add = set(result.get("roles_to_add", ()))

            staff_member: Optional[discord.Member] = interaction.guild.get_member(self.staff_id)
            if staff_member is None:
                try:
                    staff_member = await interaction.guild.fetch_member(self.staff_id)
                except Exception:
                    await interaction.followup.send(embed=simple_embed("Failed to fetch the staff member", 'cross'), ephemeral=True)
                    return
                
            current_roles = set(staff_member.roles)

                
            remove_roles = {
                interaction.guild.get_role(rid)
                for rid in roles_to_remove
            }
            remove_roles = {r for r in remove_roles if r}

            add_roles = {
                interaction.guild.get_role(rid)
                for rid in roles_to_add
            }
            add_roles = {r for r in add_roles if r}

            new_roles = (current_roles - remove_roles) | add_roles

            await staff_member.edit(
                roles=list(new_roles),
                reason="LOA assigned"
            )

            await staff_member.send(
                embed=loa_accept_embed(interaction.user.id, interaction.guild.name)
            )
            await self.disable_buttons(interaction, "accept")
            await interaction.followup.send(embed=simple_embed(f"{result.get('message')}"), ephemeral=True)

        else:
            await interaction.followup.send(embed=simple_embed(f"Failed to add LOA due to internal error {result.get('message')}", 'cross'), ephemeral=True)

    async def reject_button_callback(self, interaction: discord.Interaction):
        assert isinstance(interaction.guild, discord.Guild)

        if self.staff_id ==  interaction.user.id:
            return await interaction.response.send_message(embed=simple_embed("You cannot reject your LOA", 'cross'), ephemeral=True)
 
        await interaction.response.send_modal(LOARejectModal(self.bot_db, interaction, self, self.staff_id))

    async def disable_buttons(self, interaction: discord.Interaction, action: str):
        self.accept_button.disabled = True
        self.reject_button.disabled = True
        actor = interaction.user.mention
        self.status_display.content = f"{'Accepted' if action == 'accept' else 'Rejected'} by {actor}"


        await interaction.edit_original_response(view=self)

class LOARejectModal(discord.ui.Modal):
    reason = discord.ui.Label(
        text="Reason",
        description="Reason for rejection.",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=True
        )
    )

    def __init__(self, bot_db: BotGlobalsDatabaseAccess, view_interaction: discord.Interaction, request_view: LOARequestView, staff_id: int) -> None:
        super().__init__(title="LOA Rejection")

        self.bot_db = bot_db
        self.view_interaction: discord.Interaction = view_interaction
        self.request_view = request_view
        self.staff_id = staff_id
    
    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert isinstance(interaction.guild, discord.Guild)
        assert isinstance(self.reason.component, discord.ui.TextInput)

        await interaction.response.defer()

        staff_member: Optional[discord.Member] = interaction.guild.get_member(self.staff_id)
        if staff_member is None:
            try:
                staff_member = await interaction.guild.fetch_member(self.staff_id)
            except Exception:
                await interaction.followup.send(embed=simple_embed("Failed to fetch the staff member", 'cross'), ephemeral=True)
                return
        """ Delete the pending entry from the database """
        await self.bot_db.delete_loa_pending(self.staff_id, interaction.guild.id)

        await staff_member.send(
            embed=loa_reject_embed(interaction.user.id, interaction.guild.name, self.reason.component.value)
        )

        await interaction.followup.send(embed=simple_embed("Successfully rejected LOA!"), ephemeral=True)
        await self.request_view.disable_buttons(self.view_interaction, "reject")

class LOARequestModal(discord.ui.Modal):
    dummy = discord.ui.TextDisplay("During your LOA All of your staff roles will be stripped of. You will recieve a DM if your LOA got accepted or rejected.")

    days = discord.ui.Label(
        text="Days",
        description="The number of days you need leave for (1d, 22d etc...)",
        component=discord.ui.TextInput(
            style=discord.TextStyle.short,
            max_length=5,
            required=True
        )
    )

    reason = discord.ui.Label(
        text="Reason",
        description="Reason for your leave.",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=True
        )
    )


    def __init__(self, bot_db: BotGlobalsDatabaseAccess) -> None:
        super().__init__(title="LOA Request")

        self.bot_db = bot_db

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """ Here Let's send an LOA view and then send in an component in loa_request channel """

        assert isinstance(self.days.component, discord.ui.TextInput)
        assert isinstance(self.reason.component, discord.ui.TextInput)
        assert isinstance(interaction.guild, discord.Guild)

        await interaction.response.defer()

        """ Check if the user already has an LOA requested.   """
        requested, reason, loa_id = await self.bot_db.has_loa_pending(interaction.user.id, interaction.guild.id)
        if requested:
            return await interaction.followup.send(embed=simple_embed(f"You already have requested an LOA with reason {reason}", 'cross'), ephemeral=True)
 

        """ Send the message to the LOA channel """
        loa_channel_id = self.bot_db.get_channel(interaction.guild.id, "loa_request")
        if loa_channel_id is None:
            return await interaction.followup.send(embed=simple_embed("LOA requests channel has not been configured on this server!", 'cross'), ephemeral=True)

        loa_channel = interaction.guild.get_channel(loa_channel_id)
        if loa_channel is None:
            return await interaction.followup.send(embed=simple_embed("I cannot fetch LOA requests channel", 'cross'), ephemeral=True)


        if isinstance(loa_channel, discord.TextChannel):
            message = await loa_channel.send(view=LOARequestView(self.bot_db, interaction.user.id, interaction.guild.id ,interaction.user.display_avatar.url, self.reason.component.value, self.days.component.value))
        else:
            return await interaction.followup.send(embed=simple_embed("LOA Channel configured must be a text channel", 'cross'), ephemeral=True)


        await self.bot_db.add_loa_pending(
            interaction.user.id,
            interaction.guild.id,
            message.id,
            self.reason.component.value,
            self.days.component.value
        )

        await interaction.followup.send(embed=simple_embed("Successfully requested LOA for you!"), ephemeral=True)

class InfractionModal(discord.ui.Modal):
    reason = discord.ui.Label(
        text="Reason",
        description="Reason for their Infraction",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=True
        )
    )

    infraction_type = discord.ui.Label(
        text="Infraction Type",
        description="What is the type of infraction issued",
        component=discord.ui.Select(
            required=True,
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Strike",
                    description="Strike this staff member. They will be notified via DM and the staff-updates channel.",
                    value="strike",
                    emoji="⛔"
                ),
                discord.SelectOption(
                    label="Warning",
                    description="Warn this staff member. They will be notified via DM only and not in staff-updates.",
                    value="warning",
                    emoji="⚠️"
                )
            ]
        )
    )

    notify = discord.ui.Label(
        text="Notify Staff",
        description="Should the staff member be notified of this infraction via DM?",
        component=discord.ui.RadioGroup(
            required=True,
            options=[
                discord.RadioGroupOption(
                    label="Yes",
                    value="yes",
                    default=True
                ),
                discord.RadioGroupOption(
                    label="No",
                    value="no"
                )
            ]
        )
    )

    expiry_date = discord.ui.Label(
        text="Expire After",
        description="When should this infraction expire? (e.g., 1d, 22d, none)",
        component=discord.ui.TextInput(
            style=discord.TextStyle.short,
            max_length=5,
            required=True
        )
    )

    proofs = discord.ui.Label(
        text="Proofs",
        description="Upload supporting evidence for this infraction. (It's DUMMY AND IT WON'T WORK)",
        component=discord.ui.FileUpload(
            required=False,
            min_values=1,
            max_values=10
        )
    )


    def __init__(self, bot_db: BotGlobalsDatabaseAccess, staff: discord.Member) -> None:
        super().__init__(title="Infraction Details")
        self.bot_db = bot_db
        self.staff: discord.Member = staff

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert isinstance(self.reason.component, discord.ui.TextInput)
        assert isinstance(self.expiry_date.component, discord.ui.TextInput)
        assert isinstance(self.infraction_type.component, discord.ui.Select)
        assert isinstance(interaction.guild, discord.Guild)
        assert isinstance(self.notify.component, discord.ui.RadioGroup)
        assert isinstance(self.proofs.component, discord.ui.FileUpload)

        await interaction.response.defer()

        payload = {
            "staff_id": self.staff.id,
            "guild_id": interaction.guild.id,
            "issued_by": interaction.user.id,
            "reason": self.reason.component.value,
            "type": self.infraction_type.component.values[0],
            "expiry_date": self.expiry_date.component.value.lower()
        }

        response = await self.bot_db.strike_staff(**payload)
        if not response.get("success"):
            await interaction.followup.send(embed=simple_embed(response.get("message") or "An unknown object has been returned and failed", "cross"))
            return
        
        message = response.get("message")
        issued_by = response.get("issued_by")
        strike_reason = response.get("reason")


        channel_id = self.bot_db.get_channel(interaction.guild.id, "staff_updates")
        assert isinstance(interaction.user, discord.Member)

        if self.notify.component.value == "yes":
            await self.staff.send(embed=infraction_embed(interaction.user, self.reason.component.value, interaction.guild.name, self.infraction_type.component.values[0]))


        await interaction.followup.send(embed=simple_embed(message or "An unknown object has been returned, but It's an success!"))

        if not self.infraction_type.component.values[0] == "strike":
            return
        
        """ Build an embed so that we can post it on the staff updates channel"""
        
        embed = discord.Embed(
            color=16777215,
            title="Infraction Information",
            description=f"### {self.staff.mention} has been issued with a {self.infraction_type.component.values[0].title()}"
        )
        embed.set_thumbnail(url=self.staff.display_avatar.url)
        embed.set_image(url=Configs.img['border'])

        """
        embed.add_field(
            name="Issued By",
            value=f"<@{issued_by}>",
            inline=False,
        )
        """

        embed.add_field(
            name="Reason",
            value=f"- {strike_reason}",
            inline=False,
        )

        """ Try fetching the staff updates channel """

        
        staff_updates_channel: discord.TextChannel | None = None

        if channel_id is not None:
            channel = interaction.guild.get_channel(channel_id)

            if channel is None:
                try:
                    channel = await interaction.guild.fetch_channel(channel_id)
                except Exception:
                    channel = None

            if isinstance(channel, discord.TextChannel):
                staff_updates_channel = channel



        """ Finally send the embed """
        if staff_updates_channel:
            await staff_updates_channel.send(
                content=self.staff.mention,
                embed=embed
            )

class RankConfigureModal(discord.ui.Modal):

    def __init__(
        self,
        db: BotGlobalsDatabaseAccess,
        roles: List[int]
    ) -> None:
        super().__init__(title="Rank Configuration")

        self.bot_db = db
        default_values = []

        for role in roles:
            default_values.append(
                discord.SelectDefaultValue(
                    id=role,
                    type=discord.SelectDefaultValueType.role
                )
            )

        self.text = discord.ui.TextDisplay(
            "Select your ranks, Ranks are decided based on your role hierarchy!. "
            "Also All of the previously configured ranks will be cleared"
        )

        self.rank_display = discord.ui.TextDisplay(
            content=(
                "Current Rank Hierarchy of this server is\n"
                + "\n".join(f"<@&{role}>" for role in roles)
            )
        )

        self.rank_roles = discord.ui.Label(
            text="Rank Roles",
            description="Select your rank roles",
            component=discord.ui.RoleSelect(
                min_values=1,
                max_values=25,
                default_values=default_values
            )
        )

        self.add_item(self.text)
        self.add_item(self.rank_display)
        self.add_item(self.rank_roles)

    async def on_submit(
        self,
        interaction: discord.Interaction
    ) -> None:
        
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be executed inside an guild", ephemeral=True)
            return
        
        assert isinstance(self.rank_roles.component, discord.ui.RoleSelect)

        ranks = {
            role.id: role.position
            for role in self.rank_roles.component.values
        }

        await self.bot_db.rank_setup(
            guild_id=interaction.guild.id,
            role_id=ranks
        )

        await interaction.response.send_message(
            embed=simple_embed(f"Configured {len(ranks)} staff ranks.")
        )
