from __future__ import annotations

import logging
import discord
import src.core.configs.bot_details as Configs

from typing import Dict, Optional
from src.core.utils.embeds.sLilyEmbed import simple_embed
from ..embeds.staff_management_embed import loa_accept_embed, loa_reject_embed, infraction_embed
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess

from typing import List, Any, Tuple

logger = logging.getLogger("lily")


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

        try:
            border_media = Configs.img['border']
        except KeyError:
            logger.exception("StaffListView: 'border' key missing from Configs.img")
            border_media = None

        if border_media is not None:
            container_items.append(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(media=border_media)
                )
            )

        self.container = discord.ui.Container(*container_items)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            try:
                await interaction.response.send_message(
                    "Only instigator has authority to access.",
                    ephemeral=True
                )
            except discord.HTTPException:
                logger.exception(
                    "StaffListView.interaction_check: failed to send ownership rejection message (user_id=%s)",
                    interaction.user.id,
                )
            return False
        return True

    async def left_paginator_callback(self, interaction: discord.Interaction):
        try:
            view = StaffListView(
                interaction,
                self.role_data,
                self.role_id,
                page=self.page - 1
            )
            await interaction.response.edit_message(view=view)
        except discord.HTTPException:
            logger.exception(
                "StaffListView.left_paginator_callback: failed to edit message (role_id=%s, page=%s)",
                self.role_id, self.page - 1,
            )
        except Exception:
            logger.exception(
                "StaffListView.left_paginator_callback: unexpected error (role_id=%s, page=%s)",
                self.role_id, self.page - 1,
            )

    async def right_paginator_callback(self, interaction: discord.Interaction):
        try:
            view = StaffListView(
                interaction,
                self.role_data,
                self.role_id,
                page=self.page + 1
            )
            await interaction.response.edit_message(view=view)
        except discord.HTTPException:
            logger.exception(
                "StaffListView.right_paginator_callback: failed to edit message (role_id=%s, page=%s)",
                self.role_id, self.page + 1,
            )
        except Exception:
            logger.exception(
                "StaffListView.right_paginator_callback: unexpected error (role_id=%s, page=%s)",
                self.role_id, self.page + 1,
            )


class LOAStaffsView(discord.ui.LayoutView):
    def __init__(self, interaction: discord.Interaction, staff_datas: List[Dict[str, Any]]):
        super().__init__()

        self.staff_datas = staff_datas
        self.interaction = interaction
        self.staff_ids = ""

        for staff_data in staff_datas:
            self.staff_ids += f'<@{staff_data.get("staff_id")}>\n'

        if not self.staff_ids:
            self.staff_ids = "No Staffs Returned"

        assert interaction.guild is not None
        self.container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content="## LOA Staffs"),
                discord.ui.TextDisplay(content="- List all the staffs who are on leave"),
                accessory=discord.ui.Thumbnail(
                    media=(
                        interaction.guild.icon.url
                        if interaction.guild.icon
                        else interaction.guild.me.display_avatar.url
                    )
                ),
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content=self.staff_ids),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        )

        self.add_item(self.container)

class StaffsView(discord.ui.LayoutView):
    def __init__(self, interaction: discord.Interaction, db: BotGlobalsDatabaseAccess, overall_details: Dict, role_users_map):
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
                accessory=discord.ui.Thumbnail(media=interaction.guild.icon.url if interaction.guild.icon else interaction.guild.me.display_avatar.url)
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content="### Server Staff Team\n- List of Role Category who has **Moderation/Administration/Management** Authority"),
            discord.ui.TextDisplay(content=f"### __Overall Details__\n"
                        f"- **ON LOA** - `{overall_details.get('staff').get('loa')}`\n"
                        f"- **Active Staffs** - `{overall_details.get('staff').get('active')}`\n"
                        f"- **Total Staffs** - `{overall_details.get('staff').get('total')}`"),
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
        try:
            selected_role_id = int(self.roles_selector.values[0])
            role_data = self.role_users_map[selected_role_id]

            view = StaffListView(interaction, role_data, selected_role_id)

            await interaction.response.send_message(
                view=view,
                ephemeral=True
            )
        except KeyError:
            logger.exception(
                "StaffsView.role_selector_callback: role_id not found in role_users_map (value=%s)",
                self.roles_selector.values[0] if self.roles_selector.values else None,
            )
            await self._safe_error_response(interaction, "That role could not be found.")
        except discord.HTTPException:
            logger.exception("StaffsView.role_selector_callback: failed to send staff list view")
        except Exception:
            logger.exception("StaffsView.role_selector_callback: unexpected error")
            await self._safe_error_response(interaction, "Something went wrong while loading that role's staff list.")

    async def loa_staffs_callback(self, interaction: discord.Interaction):
        assert isinstance(interaction.guild, discord.Guild)
        try:
            staff_datas: List[Dict[str, Any]] = await self.db.fetch_loa_staffs(interaction.guild.id, "staff")
            view = LOAStaffsView(interaction, staff_datas)
            await interaction.response.send_message(view=view, ephemeral=True)
        except discord.HTTPException:
            logger.exception(
                "StaffsView.loa_staffs_callback: failed to send LOA staffs view (guild_id=%s)",
                interaction.guild.id,
            )
        except Exception:
            logger.exception(
                "StaffsView.loa_staffs_callback: failed to fetch/display LOA staffs (guild_id=%s)",
                interaction.guild.id,
            )
            await self._safe_error_response(interaction, "Couldn't load the LOA staff list right now.")

    async def _safe_error_response(self, interaction: discord.Interaction, message: str):
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=simple_embed(message, 'cross'), ephemeral=True)
            else:
                await interaction.response.send_message(embed=simple_embed(message, 'cross'), ephemeral=True)
        except discord.HTTPException:
            logger.exception("StaffsView._safe_error_response: failed to notify user of error")

    async def on_timeout(self):
        self.roles_selector.disabled = True
        self.loa_staffs_btn.disabled = True
        if self.message is None:
            return
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            logger.exception(
                "StaffsView.on_timeout: failed to edit message on timeout (message_id=%s)",
                self.message.id,
            )

class LOARequestView(discord.ui.LayoutView):
    def __init__(self, bot_db: BotGlobalsDatabaseAccess, staff_id: int, guild_id: int, staff_pfp: str, reason: str, days: str) -> None:
        super().__init__(timeout=None)

        self.staff_id = staff_id
        self.reason = reason
        self.days = days
        self.bot_db = bot_db

        self.accept_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=Configs.emoji["checked"],
            custom_id=f"loa-accept{staff_id}{guild_id}",
        )

        self.reject_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=Configs.emoji["cross"],
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

        if self.staff_id == interaction.user.id:
            try:
                return await interaction.response.send_message(embed=simple_embed("You cannot accept your LOA", 'cross'), ephemeral=True)
            except discord.HTTPException:
                logger.exception(
                    "LOARequestView.accept_button_callback: failed to send self-accept rejection (staff_id=%s)",
                    self.staff_id,
                )
                return

        try:
            await interaction.response.defer()
        except discord.HTTPException:
            logger.exception(
                "LOARequestView.accept_button_callback: failed to defer interaction (staff_id=%s)",
                self.staff_id,
            )
            return

        try:
            result = await self.bot_db.add_loa(
                interaction.guild.id,
                self.staff_id,
                self.reason,
                interaction.user.id
            )
        except Exception:
            logger.exception(
                "LOARequestView.accept_button_callback: add_loa DB call failed (guild_id=%s, staff_id=%s)",
                interaction.guild.id, self.staff_id,
            )
            await self._safe_followup(interaction, "Failed to add LOA due to an internal error.")
            return

        if result.get("success"):
            """ Removing the pending from LOA """
            try:
                await self.bot_db.delete_loa_pending(self.staff_id, interaction.guild.id)
            except Exception:
                logger.exception(
                    "LOARequestView.accept_button_callback: delete_loa_pending failed (staff_id=%s, guild_id=%s)",
                    self.staff_id, interaction.guild.id,
                )

            roles_to_remove = set(result.get("roles_to_remove", ()))
            roles_to_add = set(result.get("roles_to_add", ()))

            staff_member: Optional[discord.Member] = interaction.guild.get_member(self.staff_id)
            if staff_member is None:
                try:
                    staff_member = await interaction.guild.fetch_member(self.staff_id)
                except discord.HTTPException:
                    logger.exception(
                        "LOARequestView.accept_button_callback: failed to fetch staff member (staff_id=%s, guild_id=%s)",
                        self.staff_id, interaction.guild.id,
                    )
                    await self._safe_followup(interaction, "Failed to fetch the staff member")
                    return
                except Exception:
                    logger.exception(
                        "LOARequestView.accept_button_callback: unexpected error fetching staff member (staff_id=%s)",
                        self.staff_id,
                    )
                    await self._safe_followup(interaction, "Failed to fetch the staff member")
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

            try:
                await staff_member.edit(
                    roles=list(new_roles),
                    reason="LOA assigned"
                )
            except discord.HTTPException:
                logger.exception(
                    "LOARequestView.accept_button_callback: failed to edit staff member roles (staff_id=%s, guild_id=%s)",
                    self.staff_id, interaction.guild.id,
                )
                await self._safe_followup(interaction, "LOA was recorded, but I couldn't update the staff member's roles. Please update them manually.")
                return

            try:
                await staff_member.send(
                    embed=loa_accept_embed(interaction.user.id, interaction.guild.name)
                )
            except discord.HTTPException:
                logger.exception(
                    "LOARequestView.accept_button_callback: failed to DM staff member acceptance notice (staff_id=%s)",
                    self.staff_id,
                )

            await self.disable_buttons(interaction, "accept")
            await self._safe_followup(interaction, f"{result.get('message')}")

        else:
            await self._safe_followup(interaction, f"Failed to add LOA due to internal error {result.get('message')}", is_error=True)

    async def reject_button_callback(self, interaction: discord.Interaction):
        assert isinstance(interaction.guild, discord.Guild)

        if self.staff_id == interaction.user.id:
            try:
                return await interaction.response.send_message(embed=simple_embed("You cannot reject your LOA", 'cross'), ephemeral=True)
            except discord.HTTPException:
                logger.exception(
                    "LOARequestView.reject_button_callback: failed to send self-reject rejection (staff_id=%s)",
                    self.staff_id,
                )
                return

        try:
            await interaction.response.send_modal(LOARejectModal(self.bot_db, interaction, self, self.staff_id))
        except discord.HTTPException:
            logger.exception(
                "LOARequestView.reject_button_callback: failed to open rejection modal (staff_id=%s)",
                self.staff_id,
            )

    async def disable_buttons(self, interaction: discord.Interaction, action: str):
        self.accept_button.disabled = True
        self.reject_button.disabled = True
        actor = interaction.user.mention
        self.status_display.content = f"{'Accepted' if action == 'accept' else 'Rejected'} by {actor}"

        try:
            await interaction.edit_original_response(view=self)
        except discord.HTTPException:
            logger.exception(
                "LOARequestView.disable_buttons: failed to edit original response (staff_id=%s, action=%s)",
                self.staff_id, action,
            )

    async def _safe_followup(self, interaction: discord.Interaction, message: str, is_error: bool = False):
        try:
            await interaction.followup.send(
                embed=simple_embed(message, 'cross') if is_error else simple_embed(message),
                ephemeral=True,
            )
        except discord.HTTPException:
            logger.exception(
                "LOARequestView._safe_followup: failed to send followup (staff_id=%s)",
                self.staff_id,
            )

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

        try:
            await interaction.response.defer()
        except discord.HTTPException:
            logger.exception(
                "LOARejectModal.on_submit: failed to defer interaction (staff_id=%s)",
                self.staff_id,
            )
            return

        staff_member: Optional[discord.Member] = interaction.guild.get_member(self.staff_id)
        if staff_member is None:
            try:
                staff_member = await interaction.guild.fetch_member(self.staff_id)
            except discord.HTTPException:
                logger.exception(
                    "LOARejectModal.on_submit: failed to fetch staff member (staff_id=%s, guild_id=%s)",
                    self.staff_id, interaction.guild.id,
                )
                await self._safe_followup(interaction, "Failed to fetch the staff member", is_error=True)
                return
            except Exception:
                logger.exception(
                    "LOARejectModal.on_submit: unexpected error fetching staff member (staff_id=%s)",
                    self.staff_id,
                )
                await self._safe_followup(interaction, "Failed to fetch the staff member", is_error=True)
                return

        """ Delete the pending entry from the database """
        try:
            await self.bot_db.delete_loa_pending(self.staff_id, interaction.guild.id)
        except Exception:
            logger.exception(
                "LOARejectModal.on_submit: delete_loa_pending failed (staff_id=%s, guild_id=%s)",
                self.staff_id, interaction.guild.id,
            )

        try:
            await staff_member.send(
                embed=loa_reject_embed(interaction.user.id, interaction.guild.name, self.reason.component.value)
            )
        except discord.HTTPException:
            logger.exception(
                "LOARejectModal.on_submit: failed to DM staff member rejection notice (staff_id=%s)",
                self.staff_id,
            )

        await self._safe_followup(interaction, "Successfully rejected LOA!")
        await self.request_view.disable_buttons(self.view_interaction, "reject")

    async def _safe_followup(self, interaction: discord.Interaction, message: str, is_error: bool = False):
        try:
            await interaction.followup.send(
                embed=simple_embed(message, 'cross') if is_error else simple_embed(message),
                ephemeral=True,
            )
        except discord.HTTPException:
            logger.exception(
                "LOARejectModal._safe_followup: failed to send followup (staff_id=%s)",
                self.staff_id,
            )

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

        try:
            await interaction.response.defer()
        except discord.HTTPException:
            logger.exception(
                "LOARequestModal.on_submit: failed to defer interaction (user_id=%s)",
                interaction.user.id,
            )
            return

        """ Check if the user already has an LOA requested.   """
        try:
            requested, reason, loa_id = await self.bot_db.has_loa_pending(interaction.user.id, interaction.guild.id)
        except Exception:
            logger.exception(
                "LOARequestModal.on_submit: has_loa_pending DB call failed (user_id=%s, guild_id=%s)",
                interaction.user.id, interaction.guild.id,
            )
            await self._safe_followup(interaction, "Something went wrong while checking your existing LOA status.", is_error=True)
            return

        if requested:
            return await self._safe_followup(interaction, f"You already have requested an LOA with reason {reason}", is_error=True)

        """ Send the message to the LOA channel """
        try:
            loa_channel_id = self.bot_db.get_channel(interaction.guild.id, "loa_request")
        except Exception:
            logger.exception(
                "LOARequestModal.on_submit: get_channel lookup failed (guild_id=%s)",
                interaction.guild.id,
            )
            await self._safe_followup(interaction, "Couldn't look up the LOA requests channel configuration.", is_error=True)
            return

        if loa_channel_id is None:
            return await self._safe_followup(interaction, "LOA requests channel has not been configured on this server!", is_error=True)

        loa_channel = interaction.guild.get_channel(loa_channel_id)
        if loa_channel is None:
            try:
                loa_channel = await interaction.guild.fetch_channel(loa_channel_id)
            except discord.HTTPException:
                logger.exception(
                    "LOARequestModal.on_submit: failed to fetch LOA requests channel (channel_id=%s, guild_id=%s)",
                    loa_channel_id, interaction.guild.id,
                )
                return await self._safe_followup(interaction, "I cannot fetch LOA requests channel", is_error=True)

        if not isinstance(loa_channel, discord.TextChannel):
            return await self._safe_followup(interaction, "LOA Channel configured must be a text channel", is_error=True)

        try:
            message = await loa_channel.send(
                view=LOARequestView(
                    self.bot_db,
                    interaction.user.id,
                    interaction.guild.id,
                    interaction.user.display_avatar.url,
                    self.reason.component.value,
                    self.days.component.value,
                )
            )
        except discord.HTTPException:
            logger.exception(
                "LOARequestModal.on_submit: failed to send LOA request view to channel (channel_id=%s, user_id=%s)",
                loa_channel.id, interaction.user.id,
            )
            await self._safe_followup(interaction, "Failed to post your LOA request. Please try again later.", is_error=True)
            return

        try:
            await self.bot_db.add_loa_pending(
                interaction.user.id,
                interaction.guild.id,
                message.id,
                self.reason.component.value,
                self.days.component.value
            )
        except Exception:
            logger.exception(
                "LOARequestModal.on_submit: add_loa_pending DB call failed (user_id=%s, guild_id=%s, message_id=%s)",
                interaction.user.id, interaction.guild.id, message.id,
            )
            await self._safe_followup(interaction, "Your LOA request was posted, but saving it failed. Please contact staff.", is_error=True)
            return

        await self._safe_followup(interaction, "Successfully requested LOA for you!")

    async def _safe_followup(self, interaction: discord.Interaction, message: str, is_error: bool = False):
        try:
            await interaction.followup.send(
                embed=simple_embed(message, 'cross') if is_error else simple_embed(message),
                ephemeral=True,
            )
        except discord.HTTPException:
            logger.exception(
                "LOARequestModal._safe_followup: failed to send followup (user_id=%s)",
                interaction.user.id,
            )

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

        try:
            await interaction.response.defer()
        except discord.HTTPException:
            logger.exception(
                "InfractionModal.on_submit: failed to defer interaction (staff_id=%s)",
                self.staff.id,
            )
            return

        payload = {
            "staff_id": self.staff.id,
            "guild_id": interaction.guild.id,
            "issued_by": interaction.user.id,
            "reason": self.reason.component.value,
            "type": self.infraction_type.component.values[0],
            "expiry_date": self.expiry_date.component.value.lower()
        }

        try:
            response = await self.bot_db.strike_staff(**payload)
        except Exception:
            logger.exception(
                "InfractionModal.on_submit: strike_staff DB call failed (staff_id=%s, guild_id=%s)",
                self.staff.id, interaction.guild.id,
            )
            await self._safe_followup(interaction, "An unknown error occurred while recording the infraction.", is_error=True)
            return

        if not response.get("success"):
            await self._safe_followup(interaction, response.get("message") or "An unknown object has been returned and failed", is_error=True)
            return

        message = response.get("message")
        issued_by = response.get("issued_by")
        strike_reason = response.get("reason")

        try:
            channel_id = self.bot_db.get_channel(interaction.guild.id, "staff_updates")
        except Exception:
            logger.exception(
                "InfractionModal.on_submit: get_channel lookup failed (guild_id=%s)",
                interaction.guild.id,
            )
            channel_id = None

        assert isinstance(interaction.user, discord.Member)

        if self.notify.component.value == "yes":
            try:
                await self.staff.send(embed=infraction_embed(interaction.user, self.reason.component.value, interaction.guild.name, self.infraction_type.component.values[0]))
            except discord.HTTPException:
                logger.exception(
                    "InfractionModal.on_submit: failed to DM staff member infraction notice (staff_id=%s)",
                    self.staff.id,
                )

        await self._safe_followup(interaction, message or "An unknown object has been returned, but It's an success!")

        if not self.infraction_type.component.values[0] == "strike":
            return

        """ Build an embed so that we can post it on the staff updates channel"""

        try:
            border_media = Configs.img['border']
        except KeyError:
            logger.exception("InfractionModal.on_submit: 'border' key missing from Configs.img")
            border_media = None

        embed = discord.Embed(
            color=16777215,
            title="Infraction Information",
            description=f"### {self.staff.mention} has been issued with a {self.infraction_type.component.values[0].title()}"
        )
        embed.set_thumbnail(url=self.staff.display_avatar.url)
        if border_media is not None:
            embed.set_image(url=border_media)

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

        staff_updates_channel: Optional[discord.TextChannel] = None

        if channel_id is not None:
            channel = interaction.guild.get_channel(channel_id)

            if channel is None:
                try:
                    channel = await interaction.guild.fetch_channel(channel_id)
                except discord.HTTPException:
                    logger.exception(
                        "InfractionModal.on_submit: failed to fetch staff updates channel (channel_id=%s, guild_id=%s)",
                        channel_id, interaction.guild.id,
                    )
                    channel = None

            if isinstance(channel, discord.TextChannel):
                staff_updates_channel = channel

        """ Finally send the embed """
        if staff_updates_channel:
            try:
                await staff_updates_channel.send(
                    content=self.staff.mention,
                    embed=embed
                )
            except discord.HTTPException:
                logger.exception(
                    "InfractionModal.on_submit: failed to post infraction embed to staff updates channel (channel_id=%s, staff_id=%s)",
                    staff_updates_channel.id, self.staff.id,
                )

    async def _safe_followup(self, interaction: discord.Interaction, message: str, is_error: bool = False):
        try:
            await interaction.followup.send(
                embed=simple_embed(message, 'cross') if is_error else simple_embed(message),
            )
        except discord.HTTPException:
            logger.exception(
                "InfractionModal._safe_followup: failed to send followup (staff_id=%s)",
                self.staff.id,
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
            try:
                await interaction.response.send_message("This command can only be executed inside an guild", ephemeral=True)
            except discord.HTTPException:
                logger.exception("RankConfigureModal.on_submit: failed to send guild-only rejection message")
            return

        assert isinstance(self.rank_roles.component, discord.ui.RoleSelect)

        ranks = {
            role.id: role.position
            for role in self.rank_roles.component.values
        }

        try:
            await self.bot_db.rank_setup(
                guild_id=interaction.guild.id,
                role_id=ranks
            )
        except Exception:
            logger.exception(
                "RankConfigureModal.on_submit: rank_setup DB call failed (guild_id=%s, ranks=%s)",
                interaction.guild.id, ranks,
            )
            try:
                await interaction.response.send_message(
                    embed=simple_embed("Failed to save rank configuration due to an internal error.", 'cross')
                )
            except discord.HTTPException:
                logger.exception("RankConfigureModal.on_submit: failed to send failure notice")
            return

        try:
            await interaction.response.send_message(
                embed=simple_embed(f"Configured {len(ranks)} staff ranks.")
            )
        except discord.HTTPException:
            logger.exception(
                "RankConfigureModal.on_submit: failed to send success message (guild_id=%s)",
                interaction.guild.id,
            )


class StrikesListView(discord.ui.LayoutView):
    def __init__(
        self,
        user: Tuple[str, str],
        strikes_list_data: Dict[str, Any],
        db: BotGlobalsDatabaseAccess,
        *,
        guild_id: int,
        staff_id: int,
    ) -> None:
        super().__init__(timeout=None)

        self.user = user
        self.strikes_list_data = strikes_list_data
        self.db = db

        self.guild_id = guild_id
        self.staff_id = staff_id

        self.channel = None
        self.message: discord.Message | None = None

        self.page = strikes_list_data["page"]
        self.max_page = strikes_list_data["max_page"]
        self.total_count = strikes_list_data["total_count"]
        page_strikes = strikes_list_data["results"]

        strike_info = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content=f"# {user[0]}'s Strike List"),
                discord.ui.TextDisplay(content=f"### Total Strikes\n- {self.total_count}"),
                accessory=discord.ui.Thumbnail(
                    media=user[1],
                ),
            ),
        )

        strikes: List[discord.ui.Item] = []

        for strike in page_strikes:
            strike_id = strike.get("strike_id")

            info_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=Configs.emoji["paper_clip"],
                custom_id=str(strike_id),
            )
            info_button.callback = self.strike_info_callback

            strikes.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=(
                            f"### {Configs.emoji["pin"]} Strike #{strike_id}\n"
                            f"> {Configs.emoji['shield']} Moderator: <@{strike['manager']}>\n"
                            f"> {Configs.emoji['pencil']} Reason: {strike['reason']}"
                        )
                    ),
                    accessory=info_button,
                )
            )

        strikes_list = discord.ui.Container(
            discord.ui.TextDisplay(content="# Strike's Overview"),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            *strikes,
        )

        self.add_item(strike_info)
        self.add_item(strikes_list)
        self.add_item(self.pagination())

    def pagination(self) -> discord.ui.ActionRow:
        row = discord.ui.ActionRow()

        prev_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=Configs.emoji["left"],
            disabled=not self.strikes_list_data["has_prev"],
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
            emoji=Configs.emoji["right"],
            disabled=not self.strikes_list_data["has_next"],
        )
        next_button.callback = self.next_button_callback
        row.add_item(next_button)

        return row

    async def _refresh_page(self, interaction: discord.Interaction, new_page: int) -> None:
        try:
            result = await self.db.fetch_staff_strikes(
                staff_id=self.staff_id,
                guild_id=self.guild_id,
                page=new_page,
            )

            new_view = StrikesListView(
                self.user,
                result,
                self.db,
                guild_id=self.guild_id,
                staff_id=self.staff_id,
            )
            new_view.message = self.message
            await interaction.response.edit_message(view=new_view, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            logger.exception(
                "Failed to refresh strikes list page=%s for guild_id=%s staff_id=%s",
                new_page,
                self.guild_id,
                self.staff_id,
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=simple_embed("Something went wrong while changing pages.", 'cross'), ephemeral=True)
            else:
                await interaction.followup.send(embed=simple_embed("Something went wrong while changing pages.", 'cross'), ephemeral=True)

    async def refresh(self) -> None:
        if self.message is None:
            logger.warning("StrikesListView.refresh called with no stored message (guild_id=%s)", self.guild_id)
            return

        try:
            result = await self.db.fetch_staff_strikes(
                staff_id=self.staff_id,
                guild_id=self.guild_id,
                page=self.page,
            )

            new_view = StrikesListView(
                self.user,
                result,
                self.db,
                guild_id=self.guild_id,
                staff_id=self.staff_id,
            )
            new_view.message = self.message

            await self.message.edit(view=new_view, allowed_mentions=discord.AllowedMentions.none())
        except (discord.NotFound, discord.HTTPException):
            logger.exception(
                "Failed to refresh strikes list (guild_id=%s staff_id=%s) — message likely expired",
                self.guild_id,
                self.staff_id,
            )

    async def previous_button_callback(self, interaction: discord.Interaction) -> None:
        await self._refresh_page(interaction, self.page - 1)

    async def next_button_callback(self, interaction: discord.Interaction) -> None:
        await self._refresh_page(interaction, self.page + 1)

    async def strike_info_callback(self, interaction: discord.Interaction) -> None:
        custom_id = interaction.custom_id
        if custom_id is None:
            return
        print(custom_id)