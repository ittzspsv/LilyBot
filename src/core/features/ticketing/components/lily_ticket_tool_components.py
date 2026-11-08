from __future__ import annotations

from typing import Dict, List, Optional, Sequence, cast, Any, TYPE_CHECKING, Callable
import re
import logging
import json

import discord
from discord.ext import commands
from discord.ext.commands import MemberConverter
from datetime import datetime
from math import ceil
from contextlib import suppress
from src.core.configs.bot_details import emoji

from src.core.configs.bot_details import (
    emoji
)

from src.core.features.moderation.components.lily_moderation_components import (
    CaseListView
)

from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.database.integrations.models import (
    Page,
    TicketLog,
    TicketPanel,
    TicketType,
)

from src.core.utils.embeds.sLilyEmbed import (
    simple_embed,
)

from src.core.features.moderation.controller.lily_moderation_controller import (
    mute_user,
    quarantine_user,
    warn
)

from src.core.database.integrations.models import (
    TicketView,
    TicketPanel,
    TicketType
)

from src.core.database.integrations.bot_globals import LilyError

if TYPE_CHECKING:
    from src.lily import Lily

logger = logging.getLogger("lily")

bot = None


async def resolve_ticket_roles(bot_db: BotGlobalsDatabaseAccess, guild_id: int, submission_json: dict) -> tuple[set[int], set[int]]:
    """(ping_roles, higher_staff_roles) as configured right now. Empty if the panel no longer exists."""
    panel_message_id = submission_json.get("message_id")
    if not panel_message_id:
        return set(), set()

    view = await bot_db.get_ticket_view(message_id=panel_message_id, guild_id=guild_id)
    if view is None:
        return set(), set()

    ticket_type = view.get_type(submission_json["ticket_name_base"])
    ping_roles = set(ticket_type.ping_roles) if ticket_type else set()

    return ping_roles, set(view.staff_role_ids)

def _discord_ts(dt: datetime | None, style: str = "f") -> str:
    return f"<t:{int(dt.timestamp())}:{style}>" if dt else "*Unknown*"


""" Modals for ticket panel moderation. """
class MuteModal(discord.ui.Modal):
    duration = discord.ui.Label(
        text="Duration",
        description="Enter the duration of the mute. Example: (3d, 1hr, 22m)",
        component=discord.ui.TextInput(
            style=discord.TextStyle.short,
            max_length=50,
        )
    )

    reason = discord.ui.Label(
        text="Reason",
        description="Enter the reason for the mute",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=512,
        )
    )

    footer = discord.ui.TextDisplay(
        'Note: Any proof attachments provided by the user will be automatically appended.'
    )


    def __init__(self, member_id: int, proofs: List[str]) -> None:
        super().__init__(title="Mute User")

        self.member_id = member_id
        self.proofs = proofs

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert isinstance(self.duration.component, discord.ui.TextInput)
        assert isinstance(self.reason.component, discord.ui.TextInput)

        if interaction.guild is None:
            await interaction.response.send_message(embed=simple_embed("Command requires guild object inorder to execute", 'cross'), ephemeral=True)
            return
        
        user: Optional[discord.Member] = None
        try:
            user = await interaction.guild.fetch_member(self.member_id)
        except discord.NotFound:
            logger.warning("MuteModal: member %s not found in guild %s", self.member_id, interaction.guild.id)
            await interaction.response.send_message(embed=simple_embed("User is not in the guild!", 'cross'), ephemeral=True)
            return
        except discord.HTTPException:
            logger.exception("MuteModal: HTTP error fetching member %s in guild %s", self.member_id, interaction.guild.id)
            await interaction.response.send_message(embed=simple_embed("Failed to fetch the member due to network error!", 'cross'), ephemeral=True)
            return
        except Exception:
            logger.exception("MuteModal: unknown error fetching member %s in guild %s", self.member_id, interaction.guild.id)
            await interaction.response.send_message(embed=simple_embed("Failed to fetch the member due to unknown error!", 'cross'), ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            await mute_user(
                interaction,
                user,
                self.duration.component.value,
                self.reason.component.value,
                self.proofs
            )
        except Exception:
            logger.exception("MuteModal: mute_user failed for member %s in guild %s", self.member_id, interaction.guild.id)
            await interaction.followup.send(embed=simple_embed("Failed to mute the user due to an unexpected error!", 'cross'), ephemeral=True)

class BanModal(discord.ui.Modal):
    reason = discord.ui.Label(
        text="Reason",
        description="Enter the reason for the ban",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=512,
        )
    )

    footer = discord.ui.TextDisplay(
        'Note: Any proof attachments provided by the user will be automatically appended.'
    )


    def __init__(self, member_id: int, proofs: List[str]) -> None:
        super().__init__(title="Ban User")

        self.member_id = member_id
        self.proofs = proofs

    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(self.reason.component, discord.ui.TextInput)

        if interaction.guild is None:
            await interaction.response.send_message(embed=simple_embed("Command requires guild object inorder to execute", 'cross'), ephemeral=True)
            return
        
        if isinstance(interaction.user, discord.User):
            await interaction.response.send_message(embed=simple_embed("Command requires member object inorder to execute", 'cross'), ephemeral=True)
            return

        member: Optional[discord.Member] = None

        try:
            member = await interaction.guild.fetch_member(self.member_id)
        except discord.NotFound:
            logger.warning("BanModal: member %s not found in guild %s", self.member_id, interaction.guild.id)
            await interaction.response.send_message(embed=simple_embed("User should be in the guild in-order to quarantine him", 'cross'), ephemeral=True)
            return
        except discord.HTTPException:
            logger.exception("BanModal: HTTP error fetching member %s in guild %s", self.member_id, interaction.guild.id)
            await interaction.response.send_message(embed=simple_embed("Failed to fetch the member due to network error!", 'cross'), ephemeral=True)
            return
        except Exception:
            logger.exception("BanModal: unknown error fetching member %s in guild %s", self.member_id, interaction.guild.id)
            await interaction.response.send_message(embed=simple_embed("Failed to fetch the member due to unknown error!", 'cross'), ephemeral=True)
            return
        
        await interaction.response.defer()

        try:
            await quarantine_user(
                interaction,
                member,
                self.reason.component.value,
                self.proofs
            )
        except Exception:
            logger.exception("BanModal: quarantine_user failed for member %s in guild %s", self.member_id, interaction.guild.id)
            await interaction.followup.send(embed=simple_embed("Failed to ban/quarantine the user due to an unexpected error!", 'cross'), ephemeral=True)

class WarnModal(discord.ui.Modal):
    reason = discord.ui.Label(
        text="Reason",
        description="Enter the reason for the warn",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            max_length=512,
        )
    )

    footer = discord.ui.TextDisplay(
        'Note: Any proof attachments provided by the user will be automatically appended.'
    )


    def __init__(self, member_id: int, proofs: List[str]) -> None:
        super().__init__(title="Warn User")

        self.member_id = member_id
        self.proofs = proofs

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(embed=simple_embed("Command requires guild object inorder to execute", 'cross'), ephemeral=True)
            return
        
        if isinstance(interaction.user, discord.User):
            await interaction.response.send_message(embed=simple_embed("Command requires member object inorder to execute", 'cross'), ephemeral=True)
            return
        
        await interaction.response.defer()

        assert isinstance(self.reason.component, discord.ui.TextInput)
        member: Optional[discord.Member] = None
        
        try:
            member = await interaction.guild.fetch_member(self.member_id)
        except discord.NotFound:
            logger.warning("WarnModal: member %s not found in guild %s", self.member_id, interaction.guild.id)
            await interaction.response.send_message(embed=simple_embed("User should be in the guild in-order to quarantine him", 'cross'), ephemeral=True)
            return
        except discord.HTTPException:
            logger.exception("WarnModal: HTTP error fetching member %s in guild %s", self.member_id, interaction.guild.id)
            await interaction.response.send_message(embed=simple_embed("Failed to fetch the member due to network error!", 'cross'), ephemeral=True)
            return
        except Exception:
            logger.exception("WarnModal: unknown error fetching member %s in guild %s", self.member_id, interaction.guild.id)
            await interaction.response.send_message(embed=simple_embed("Failed to fetch the member due to unknown error!", 'cross'), ephemeral=True)
            return
        
        try:
            await warn(
                interaction,
                member,
                self.reason.component.value,
                self.proofs
            )
        except Exception:
            logger.exception("WarnModal: warn failed for member %s in guild %s", self.member_id, interaction.guild.id)
            await interaction.followup.send(embed=simple_embed("Failed to warn the user due to an unexpected error!", 'cross'), ephemeral=True)

class TicketRatingModal(discord.ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="Ticket Feedback", timeout=600)

    rating = discord.ui.Label(
        text="Ticket Support Rating",
        description="Share your experience and rate the support you received!",
        component=discord.ui.RadioGroup(
            required=True,
            options=[
                discord.RadioGroupOption(
                    label="Poor",
                    description="Support was unsatisfactory, slow, or failed to resolve the issue."
                ),
                discord.RadioGroupOption(
                    label="Fair",
                    description="Some help was provided, but overall experience was below expectations."
                ),
                discord.RadioGroupOption(
                    label="Good",
                    description="Issue was handled adequately with acceptable service."
                ),
                discord.RadioGroupOption(
                    label="Great",
                    description="Helpful, efficient support with a positive experience."
                ),
                discord.RadioGroupOption(
                    label="Excellent",
                    description="Outstanding, fast, and highly effective support experience."
                ),
            ]
        )
    )

    rating_feedback = discord.ui.Label(
        text="Support Experience",
        description="Share your ticket support experience and overall satisfaction.",
        component=discord.ui.TextInput(
            style=discord.TextStyle.long,
            max_length=512,
        ),
    )

    async def on_submit(self, interaction: discord.Interaction):
        ...

def build_ticket_summary(submission_json: dict) -> discord.Embed:
    base_name = submission_json.get("ticket_name_base", "ticket")
    ticket_name: str = base_name.replace("_", " ").title()

    roles = submission_json.get("ping_roles", [])
    ticket_mentions: str = " ".join(f"<@&{role_id}>" for role_id in roles) if roles else "No Mentions!"

    description_parts: list[str] = [f"**Type:** {ticket_name}"]

    opener_details: dict = submission_json.get("opener", {}) or {}

    if opener_details:
        description_parts.append(
            f"### Ticket Opener | {opener_details.get('member_id', 0)}\n"
            f"- **ID**: {opener_details.get('member_id', 0)}\n"
            f"- **Created on**: {opener_details.get('created_on')}\n"
            f"- **Joined on**: {opener_details.get('joined_on')}"
        )
    else:
        description_parts.append("### Ticket Opener\nUser information unavailable")

    field_data = submission_json.get("field_data", []) or []

    for data in field_data:
        field = data.get("field", {}) or {}
        value = data.get("value")

        field_type = field.get("type")
        label = field.get("label", "label")

        if field_type in ("short", "long"):
            description_parts.append(f"### {label}\n{value}")

        elif field_type == "member":
            if isinstance(value, dict) and value.get("flag") == 0:
                description_parts.append(
                    f"### {label} | {value['member_id']}\n"
                    f"- **ID**: {value['member_id']}\n"
                    f"- **Created on**: {value['created_on']}\n"
                    f"- **Joined on**: {value['joined_on']}"
                )
            else:
                username = value["username"] if isinstance(value, dict) else value
                description_parts.append(f"### {label}\n{username}")

        elif field_type == "role_select":
            description_parts.append(f"### {label}\n{' , '.join(value)}")

        elif field_type in ("selector", "radio_option", "check_box"):
            picked = value if isinstance(value, list) else [value]
            description_parts.append(f"### {label}\n{' , '.join(str(v) for v in picked if v) or 'None selected'}")

    embed = discord.Embed(
        title="Ticket Summary",
        description="\n\n".join(description_parts),
    )

    avatar = opener_details.get("avatar")
    if avatar:
        embed.set_thumbnail(url=avatar)

    return embed

class TicketOpenerComponent(discord.ui.LayoutView):
    def __init__(
        self,
        submission_json: dict,
        ticket_channel_id: int,
    ) -> None:
        super().__init__(timeout=None)

        base_name = submission_json.get("ticket_name_base", "ticket")
        ticket_name: str = base_name.replace("_", " ").title()
        roles = submission_json.get("ping_roles", [])
        ticket_mentions: str = " ".join(f"<@&{role_id}>" for role_id in roles) if roles else "No Mentions!"

        opener_details: dict = submission_json.get("opener") or {}
        self.ticket_channel_id: int = ticket_channel_id

        self.submission_json = submission_json

        content = (
            f"> {emoji['user']} **User**: <@{opener_details.get('member_id', 0)}>\n"
            f"> {emoji['pencil']} **ID**: {opener_details.get('member_id', 0)}\n"
            f"> {emoji['calender']} **Created on**: {opener_details.get('created_on')}\n"
            f"> {emoji['calender']} **Joined on**: {opener_details.get('joined_on')}"
            if opener_details
            else "**User information unavailable**"
        )

        self.claim_ticket: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["user_claim"],
            label="Claim Ticket",
            custom_id=f"claim-ticket{self.ticket_channel_id}",
        )

        self.revoke_claim: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["user_unclaim"],
            label="Revoke Claim",
            custom_id=f"revoke-claim{self.ticket_channel_id}",
        )

        self.claim_ticket.callback = self.claim_ticket_callback
        self.revoke_claim.callback = self.revoke_claim_callback

        container = discord.ui.Container(
            discord.ui.TextDisplay(content=f"# {ticket_name}"),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.Section(
                discord.ui.TextDisplay(
                    content=f"### Ticket Opener Information"
                ),
                discord.ui.TextDisplay(content=content),
                accessory=discord.ui.Thumbnail(
                    media=opener_details.get("avatar", 0),
                ),
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content=f"-# {ticket_mentions}"),
        )

        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.claim_ticket, self.revoke_claim))

    async def claim_ticket_callback(self, interaction: discord.Interaction) -> None:
        if interaction.channel is None or interaction.guild is None:
            return

        await interaction.response.defer()
        assert isinstance(interaction.user, discord.Member)

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        try:
            allowed_roles, _ = await resolve_ticket_roles(
                bot_db, interaction.guild.id, self.submission_json
            )
        except Exception:
            logger.exception(
                "TicketOpenerComponent.claim_ticket_callback: resolve_ticket_roles failed for channel %s",
                interaction.channel.id
            )
            await interaction.followup.send(
                embed=simple_embed("Failed to verify your permissions due to a database error!", 'cross'),
                ephemeral=True
            )
            return

        is_staff = any(role.id in allowed_roles for role in interaction.user.roles)

        if not is_staff:
            await interaction.followup.send(
                embed=simple_embed("You are not allowed to claim this ticket!", 'cross'),
                ephemeral=True
            )
            return

        try:
            success = await bot_db.set_ticket_claimer(
                interaction.user.id, interaction.channel.id, interaction.guild.id
            )
        except Exception:
            logger.exception(
                "TicketOpenerComponent.claim_ticket_callback: set_ticket_claimer failed for channel %s in guild %s",
                interaction.channel.id, interaction.guild.id
            )
            await interaction.followup.send(embed=simple_embed("Failed to claim the ticket due to a database error!", 'cross'), ephemeral=True)
            return

        if not success:
            try:
                ticket = await bot_db.get_ticket_by_id(interaction.channel.id)
                claimer = ticket.claimer_user_id if ticket else None
            except Exception:
                logger.exception(
                    "TicketOpenerComponent.claim_ticket_callback: get_ticket_by_id failed for channel %s",
                    interaction.channel.id
                )
                await interaction.followup.send(embed=simple_embed("This ticket is already claimed, but the claimer could not be determined.", 'cross'), ephemeral=True)
                return

            if claimer is None:
                await interaction.followup.send(embed=simple_embed("This ticket is already claimed, but the claimer could not be determined.", 'cross'), ephemeral=True)
                return

            await interaction.followup.send(
                embed=simple_embed(f"<@{claimer}> has already claimed this ticket!", 'cross'),
                ephemeral=True
            )
            return

        channel = interaction.channel
        if isinstance(channel, discord.TextChannel) and isinstance(interaction.user, discord.Member):
            try:
                await channel.set_permissions(
                    interaction.user,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    add_reactions=True,
                    use_external_emojis=True,
                    read_message_history=True
                )
            except discord.Forbidden:
                logger.exception(
                    "TicketOpenerComponent.claim_ticket_callback: missing permissions to set overwrites in channel %s",
                    channel.id
                )
            except discord.HTTPException:
                logger.exception(
                    "TicketOpenerComponent.claim_ticket_callback: HTTP error setting permissions in channel %s",
                    channel.id
                )

        self.claim_ticket.disabled = True
        self.claim_ticket.label = "Claimed"
        self.claim_ticket.style = discord.ButtonStyle.secondary

        assert interaction.message is not None
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            logger.exception(
                "TicketOpenerComponent.claim_ticket_callback: failed to edit ticket message %s",
                interaction.message.id
            )
        await interaction.followup.send(embed=simple_embed(f"{interaction.user.mention} has claimed the ticket!"))

    async def revoke_claim_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        if interaction.channel is None or interaction.guild is None:
            return

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        try:
            ticket = await bot_db.get_ticket_by_id(interaction.channel.id)
            claimer = ticket.claimer_user_id if ticket else None
        except Exception:
            logger.exception(
                "TicketOpenerComponent.revoke_claim_callback: get_ticket_by_id failed for channel %s",
                interaction.channel.id
            )
            await interaction.followup.send(embed=simple_embed("Failed to look up the ticket claimer due to a database error!", 'cross'), ephemeral=True)
            return

        if claimer is None:
            await interaction.followup.send(
                embed=simple_embed("No one has claimed this ticket!", 'cross'),
                ephemeral=True
            )
            return

        claimer_member: Optional[discord.Member] = None
        try:
            claimer_member = await interaction.guild.fetch_member(claimer)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.exception(
                "TicketOpenerComponent.revoke_claim_callback: failed to fetch claimer %s in guild %s",
                claimer, interaction.guild.id
            )
            claimer_member = None

        assert isinstance(interaction.user, discord.Member)
        can_revoke = interaction.user.id == claimer
        if not can_revoke:
            try:
                _, higher_staff_role_ids = await resolve_ticket_roles(
                    bot_db, interaction.guild.id, self.submission_json
                )
            except Exception:
                logger.exception(
                    "TicketOpenerComponent.revoke_claim_callback: resolve_ticket_roles failed for channel %s",
                    interaction.channel.id
                )
                await interaction.followup.send(
                    embed=simple_embed("Failed to verify your permissions due to a database error!", 'cross'),
                    ephemeral=True
                )
                return

            can_revoke = any(role.id in higher_staff_role_ids for role in interaction.user.roles)

        if not can_revoke:
            await interaction.followup.send(
                embed=simple_embed("You are not allowed to revoke ticket claims!", 'cross'),
                ephemeral=True
            )
            return

        channel = interaction.channel
        if claimer_member is not None and isinstance(channel, discord.TextChannel):
            try:
                await channel.set_permissions(claimer_member, overwrite=None)
            except discord.Forbidden:
                logger.exception(
                    "TicketOpenerComponent.revoke_claim_callback: missing permissions to clear overwrites in channel %s",
                    channel.id
                )
            except discord.HTTPException:
                logger.exception(
                    "TicketOpenerComponent.revoke_claim_callback: HTTP error clearing permissions in channel %s",
                    channel.id
                )

        self.claim_ticket.disabled = False
        self.claim_ticket.label = "Claim"
        self.claim_ticket.style = discord.ButtonStyle.secondary

        try:
            await bot_db.reset_ticket_claimer(interaction.channel.id)
        except Exception:
            logger.exception(
                "TicketOpenerComponent.revoke_claim_callback: reset_ticket_claimer failed for channel %s",
                interaction.channel.id
            )

        if interaction.message:
            try:
                await interaction.message.edit(view=self)
            except discord.HTTPException:
                logger.exception(
                    "TicketOpenerComponent.revoke_claim_callback: failed to edit ticket message %s",
                    interaction.message.id
                )

        await interaction.followup.send(
            embed=simple_embed("Ticket claim has been revoked!"),
            ephemeral=True
        )

        assert isinstance(channel, discord.TextChannel)
        try:
            await channel.send(
                embed=simple_embed(f"{interaction.user.mention} revoked the ticket claim.")
            )
        except discord.HTTPException:
            logger.exception(
                "TicketOpenerComponent.revoke_claim_callback: failed to send revoke notice in channel %s",
                channel.id
            )

class TicketComponentEmbed(discord.ui.LayoutView):
    def __init__(self, 
                 ticket_channel_id: int, 
                 submission_json: dict, 
                 buttons: bool = True # Either to invoke buttons or just create a stale view
        ):

        timeout = None if buttons else 10
        super().__init__(timeout=timeout)

        self.buttons = buttons
        
        self.ticket_channel_id: int = ticket_channel_id
        self.misc: Dict = {}

        self.submission_json = submission_json

        base_name = self.submission_json.get("ticket_name_base", "ticket")
        self.ticket_name: str = base_name.replace("_", " ").title()
        roles = submission_json.get("ping_roles", [])
        self.ticket_mentions: str = " ".join(f"<@&{role_id}>" for role_id in roles) if roles else "No Mentions!"


        if buttons:
            self.case_list_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=emoji["logs"],
                custom_id=f"case-list{self.ticket_channel_id}",
            )


            self.ban_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=emoji["ban_hammer"],
                custom_id=f"ban{self.ticket_channel_id}",
            )


            self.mute_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=emoji["member"],
                custom_id=f"mute{self.ticket_channel_id}",
            )


            self.warn_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=emoji["warn"],
                custom_id=f"warn{self.ticket_channel_id}",
            )

            self.ban_button.callback = self.ban_callback
            self.mute_button.callback = self.mute_callback
            self.warn_button.callback = self.warn_callback
            self.case_list_button.callback = self.case_list_callback

        ticket_details = []
        field_data = self.submission_json["field_data"]

        for data in field_data:
            field = data.get("field")
            value = data.get("value")

            field_type = field.get("type")
            label = field.get("label", "label")

            if field_type in ("short", "long"):
                
                ticket_details.append(
                    discord.ui.TextDisplay(
                        f"### {label}\n> {value}"
                    )
                )

            elif field_type == "member":
                if value["flag"] == 0:
                    self.misc["reported_member"] = {
                        "id": value["member_id"],
                        "avatar": value["avatar"],
                        "username": value["username"]
                    }

                    ticket_details.append(
                        discord.ui.Section(
                            discord.ui.TextDisplay(content=f"### {label} | <@{value["member_id"]}>"),
                            discord.ui.TextDisplay(content=f"- **ID**: **{value["member_id"]}**\n- **Created on**: {value["created_on"]}\n- **Joined on**: {value["joined_on"]}"),
                            accessory=discord.ui.Thumbnail(
                                media=value["avatar"],
                            ),
                        )
                    )
                    if buttons:
                        ticket_details.append(
                            discord.ui.ActionRow(
                                self.case_list_button,
                                self.ban_button,
                                self.mute_button,
                                self.warn_button
                            )
                        )
                else:
                    ticket_details.append(
                    discord.ui.TextDisplay(
                        f"### {label}\n> {value["username"]}"
                    )
                )

                ticket_details.append(
                    discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
                )

            elif field_type in ("file_upload",):

                self.misc["proofs"] = value
                
                gallery = discord.ui.MediaGallery()
                gallery.items = [discord.MediaGalleryItem(media=url) for url in value]
                ticket_details.append(
                    discord.ui.TextDisplay(
                        f"### {label}"
                    )
                )
                ticket_details.append(
                    gallery
                )

                ticket_details.append(
                    discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
                )

            elif field_type in ("role_select",):
                ticket_details.append(
                    discord.ui.TextDisplay(
                        f"### {label}\n> {' , '.join(value)}"
                    )
                )

            elif field_type in ("guild_invite",):
                if value["flag"] == 0:
                    guild_icon = value.get("icon") or "https://img.icons8.com/?size=100&id=2mIgusGquJFz&format=png&color=000000"
                    ticket_details.append(
                        discord.ui.Section(
                            discord.ui.TextDisplay(content=f"### {value.get('name', 'Unknown server')}"),
                            discord.ui.TextDisplay(
                                content=(
                                    f"- **Member Count: **: {value['member_count']}\n"
                                    f"- **Guild Owner: **: <@{value['owner_id']}>"
                                )
                            ),
                            accessory=discord.ui.Thumbnail(media=guild_icon)
                        )
                    )

                    ticket_details.append(
                        discord.ui.ActionRow(
                            discord.ui.Button(
                                label="Invite URL",
                                style=discord.ButtonStyle.link,
                                url=value["invite_url"]
                            )
                        )
                    )

                else:
                    ticket_details.append(
                        discord.ui.TextDisplay(content=value["invite_url"])
                    )

            elif field_type in ("selector", "radio_option", "check_box"):
                picked = value if isinstance(value, list) else [value]
                answers = " , ".join(str(v) for v in picked if v) or "None selected"

                ticket_details.append(
                    discord.ui.TextDisplay(
                        f"### {label}\n> {answers}"
                    )
                )



        ticket_details_container = discord.ui.Container(
            discord.ui.TextDisplay(
                "## Ticket Details"
            ),
            *ticket_details
        )

        self.add_item(ticket_details_container)

    async def _check_permissions(self, interaction: discord.Interaction) -> bool:
        assert isinstance(interaction.user, discord.Member)

        if interaction.guild is None:
            return False

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        # Read on demand so edits to the ticket config also apply to tickets that are already open.
        try:
            allowed_roles, _ = await resolve_ticket_roles(
                bot_db, interaction.guild.id, self.submission_json
            )
        except Exception:
            logger.exception(
                "TicketComponentEmbed._check_permissions: resolve_ticket_roles failed for channel %s",
                self.ticket_channel_id
            )
            await interaction.response.send_message(
                embed=simple_embed("Failed to verify your permissions due to a database error!", 'cross'),
                ephemeral=True
            )
            return False

        is_staff = any(role.id in allowed_roles for role in interaction.user.roles)

        if not is_staff:
            await interaction.response.send_message(
                embed=simple_embed("You are not allowed to use this!", 'cross'),
                ephemeral=True
            )
            return False

        return True

    async def case_list_callback(self, interaction: discord.Interaction):
        if not await self._check_permissions(interaction):
            return
        if interaction.guild is None:
            return
        
        """ Get member id """
        
        """ Fetch modlogs of the reported member """
        reported_member_data = self.misc["reported_member"]
        await self.case_list_handler(interaction, reported_member_data)
        
    async def case_list_handler(self, interaction: discord.Interaction, member_data: dict) -> None:

        assert isinstance(interaction.guild, discord.Guild)

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        _guild_id = interaction.guild.id

        try:
            result = await bot_db.fetch_mod_logs(_guild_id, member_data["id"])
        except Exception:
            logger.exception(
                "TicketComponentEmbed.case_list_handler: fetch_mod_logs failed for user %s in guild %s",
                member_data["id"], _guild_id
            )
            await interaction.response.send_message(embed=simple_embed("Failed to fetch mod logs due to a database error!", 'cross'), ephemeral=True)
            return

        if result.total_count == 0:
            await interaction.response.send_message(embed=simple_embed("No cases found.", 'cross'), ephemeral=True)
            return  

        view = CaseListView((member_data["username"], member_data["avatar"]), result, bot_db, guild_id=interaction.guild.id, target_user_id=member_data["id"], interactor=interaction.user.id)
        try:
            await interaction.response.send_message(
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
                ephemeral=True
            )
        except discord.HTTPException:
            logger.exception(
                "TicketComponentEmbed.case_list_handler: failed to send case list for user %s",
                member_data["id"]
            )

    async def ban_callback(self, interaction: discord.Interaction):
        if not await self._check_permissions(interaction):
            return

        try:
            await interaction.response.send_modal(
                BanModal(
                    member_id=self.misc["reported_member"]["id"],
                    proofs=self.misc["proofs"]
                )
            )
        except Exception:
            logger.exception(
                "TicketComponentEmbed.ban_callback: failed to open BanModal for channel %s",
                self.ticket_channel_id
            )

    async def mute_callback(self, interaction: discord.Interaction):
        if not await self._check_permissions(interaction):
            return

        try:
            await interaction.response.send_modal(
                MuteModal(
                    member_id=self.misc["reported_member"]["id"],
                    proofs=self.misc["proofs"]
                )
            )
        except Exception:
            logger.exception(
                "TicketComponentEmbed.mute_callback: failed to open MuteModal for channel %s",
                self.ticket_channel_id
            )

    async def warn_callback(self, interaction: discord.Interaction):
        if not await self._check_permissions(interaction):
            return

        try:
            await interaction.response.send_modal(
                WarnModal(
                    member_id=self.misc["reported_member"]["id"],
                    proofs=self.misc["proofs"]
                )
            )
        except Exception:
            logger.exception(
                "TicketComponentEmbed.warn_callback: failed to open WarnModal for channel %s",
                self.ticket_channel_id
            )

class TicketModal(discord.ui.Modal):
    def __init__(self, title: str, ticket: TicketType, view_id: int, message: discord.Message):
        super().__init__(title=title)

        if not isinstance(ticket, TicketType):
            raise TypeError(f"ticket must be a TicketType, got {type(ticket)}")

        self.components: List[Dict] = []
        self.ticket = ticket
        self.view_id = view_id
        self.converter = MemberConverter()
        self.message = message

        self.fields = self.ticket.fields

        if not isinstance(self.fields, list):
            raise TypeError(f"fields must be a list, got {type(self.fields)}")

        for field in self.fields:
            if not isinstance(field, dict):
                raise TypeError(f"Each field must be a dict, got {type(field)}")

            label = field.get("label", "")
            description = field.get("description", "")
            length = field.get("length", 100)
            field_type = field.get("type", "short")

            component = None

            """ Assign Components based on field type """
            if field_type in ("member", "long", "short", "guild_invite"):
                style = (
                    discord.TextStyle.paragraph
                    if field_type == "long"
                    else discord.TextStyle.short
                )

                component=discord.ui.TextInput(
                    style=style,
                    max_length=length,
                    required=True
                )
            elif field_type == "file_upload":
                component = discord.ui.FileUpload(
                    max_values=10,
                    custom_id="report_images",
                    required=True
                )

            elif field_type == "role_select":
                component = discord.ui.RoleSelect(
                    min_values=1,
                    max_values=1,
                    required=True
                )

            elif field_type in ("selector", "radio_option", "check_box"):
                options = self.parse_field_options(field)

                if field_type == "selector":
                    if not 1 <= len(options) <= 25:
                        raise ValueError(f"selector '{label}' needs 1-25 options")
                    min_values, max_values = self.selection_range(field, len(options), cap=25, default_max=1)
                    component = discord.ui.Select(
                        min_values=min_values,
                        max_values=max_values,
                        required=True,
                        options=[discord.SelectOption(label=o[:100], value=o[:100]) for o in options],
                    )

                elif field_type == "radio_option":
                    if not 2 <= len(options) <= 10:
                        raise ValueError(f"radio field '{label}' needs 2-10 options")
                    component = discord.ui.RadioGroup(
                        required=True,
                        options=[discord.RadioGroupOption(label=o[:100]) for o in options],
                    )

                else:
                    if not 1 <= len(options) <= 10:
                        raise ValueError(f"checkbox field '{label}' needs 1-10 options")

                    if len(options) == 1:
                        description = description or options[0][:100]
                        component = discord.ui.Checkbox(default=False)
                    else:
                        min_values, max_values = self.selection_range(
                            field, len(options), cap=10, default_max=len(options)
                        )
                        component = discord.ui.CheckboxGroup(
                            min_values=min_values,
                            max_values=max_values,
                            required=True,
                            options=[discord.CheckboxGroupOption(label=o[:100]) for o in options],
                        )

            """ This wouldn't likely to occur """
            if component is None:
                raise ValueError

            item = discord.ui.Label(
                text=label,
                description=description if description else None,
                component=component
            )

            self.components.append({
                "field": field,
                "item": item
            })
            self.add_item(item)
        
    def parse_field_options(self, field: dict) -> list[str]:
        raw = field.get("metadata") or ""
        return list(dict.fromkeys(o.strip() for o in str(raw).split(",") if o.strip()))


    def selection_range(self, field: dict, option_count: int, *, cap: int, default_max: int) -> tuple[int, int]:
        ceiling = min(option_count, cap)
        try:
            min_values = int(field.get("min_values", 1))
            max_values = int(field.get("max_values", default_max))
        except (TypeError, ValueError):
            min_values, max_values = 1, default_max
        max_values = max(1, min(max_values, ceiling))
        min_values = max(1, min(min_values, max_values))
        return min_values, max_values


    async def ticket_thread_constructor(self, interaction: discord.Interaction, submission_json: dict, logging_channel_id: int, higher_staff_roles_ids: List[int]) -> discord.TextChannel | discord.Thread | None:
        if interaction.guild is None:
            return None

        raw_channel_id = submission_json.get("channel_id")
        if raw_channel_id is None:
            logger.error(
                "TicketModal.ticket_thread_constructor: ticket type has no category channel in guild %s",
                interaction.guild.id
            )
            await interaction.followup.send(
                embed=simple_embed("Misconfigured ticket category. Please contact an admin."),
                ephemeral=True
            )
            return None

        channel_id: int = int(raw_channel_id)
        
        proof_attachments = submission_json.get("proof_images")
        proofs_flag = False
        if proof_attachments:
            proof_url = '\n'.join(proof_attachments)
            proofs_flag = True
        else:
            proof_url = "No Proofs Attached!"
            proofs_flag = False

        roles = submission_json.get("ping_roles", [])

        opener = interaction.user
        ticket_name_base: str = submission_json["ticket_name_base"]
        channel_emoji = submission_json.get("channel_emoji", "")
        ticket_name = f"{channel_emoji}{ticket_name_base}"
    
        channel_category = interaction.guild.get_channel(channel_id)

        if not isinstance(channel_category, discord.CategoryChannel):
            try:
                channel_category = await interaction.guild.fetch_channel(channel_id)
            except discord.NotFound:
                logger.exception(
                    "TicketModal.ticket_thread_constructor: category channel %s not found in guild %s",
                    channel_id, interaction.guild.id
                )
                channel_category = None
            except discord.HTTPException:
                logger.exception(
                    "TicketModal.ticket_thread_constructor: HTTP error fetching category channel %s in guild %s",
                    channel_id, interaction.guild.id
                )
                channel_category = None

        if not isinstance(channel_category, discord.CategoryChannel):
            logger.error(
                "TicketModal.ticket_thread_constructor: misconfigured ticket category %s in guild %s",
                channel_id, interaction.guild.id
            )
            await interaction.followup.send(
                embed=simple_embed("Misconfigured ticket category. Please contact an admin."),
                ephemeral=True
            )
            return None


        overwrites = {}

        overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(
            view_channel=False
        )
        overwrites[opener] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
            add_reactions=True,
            use_external_emojis=True,
            read_message_history=True,
            create_public_threads=True,
            create_private_threads=False,
            send_messages_in_threads=False
        )

        overwrites[interaction.guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
            add_reactions=True,
            use_external_emojis=True,
            use_external_stickers=True,
            read_message_history=True,
            create_public_threads=True,
            create_private_threads=True,
            send_messages_in_threads=True,
            manage_channels=True,
            manage_threads=True,
            mention_everyone=True
        )

        for role_id in roles:
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    embed_links=True,
                    attach_files=True,
                    add_reactions=True,
                    use_external_emojis=True,
                    read_message_history=True,
                    create_public_threads=False,
                    create_private_threads=False,
                    send_messages_in_threads=False
                )
        for role_id in higher_staff_roles_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    add_reactions=True,
                    use_external_emojis=True,
                    read_message_history=True,
                    create_public_threads=False,
                    create_private_threads=False,
                    send_messages_in_threads=False
                )

        try:
            if isinstance(channel_category, discord.CategoryChannel):
                text_channel: discord.TextChannel = await interaction.guild.create_text_channel(
                    name=f"{ticket_name}-{opener.name}",
                    category=channel_category,
                    overwrites=overwrites
                )
            else:
                text_channel: discord.TextChannel = await interaction.guild.create_text_channel(
                    name=f"{ticket_name}-{opener.name}",
                    overwrites=overwrites
                )
        except discord.Forbidden:
            logger.exception(
                "TicketModal.ticket_thread_constructor: missing permissions to create ticket channel in guild %s",
                interaction.guild.id
            )
            await interaction.followup.send(
                embed=simple_embed("I don't have permission to create the ticket channel!", 'cross'),
                ephemeral=True
            )
            return None
        
        except discord.HTTPException as e:
            if e.code == 50035:
                logger.warning(
                    "TicketModal.ticket_thread_constructor: invalid form body creating ticket channel in guild %s: %s",
                    interaction.guild.id, e.text
                )
                if channel_category is not None and "parent_id" in str(e.text):
                    logger.warning(
                        "TicketModal.ticket_thread_constructor: category %s full in guild %s, retrying without category",
                        channel_id, interaction.guild.id
                    )
                    try:
                        text_channel: discord.TextChannel = await interaction.guild.create_text_channel(
                            name=f"{ticket_name}-{opener.name}",
                            overwrites=overwrites
                        )

                    except discord.Forbidden:
                        logger.exception(
                            "TicketModal.ticket_thread_constructor: missing permissions to create fallback ticket channel in guild %s",
                            interaction.guild.id
                        )
                        await interaction.followup.send(
                            embed=simple_embed("I don't have permission to create the ticket channel!", 'cross'),
                            ephemeral=True
                        )
                        return None
                    
                    except discord.HTTPException:
                        logger.exception(
                            "TicketModal.ticket_thread_constructor: HTTP error creating fallback ticket channel in guild %s",
                            interaction.guild.id
                        )
                        await interaction.followup.send(
                            embed=simple_embed("Failed to create the ticket channel due to a Discord API error!", 'cross'),
                            ephemeral=True
                        )
                        return None
                else:
                    await interaction.followup.send(
                        embed=simple_embed(f"Discord rejected the channel creation request: {e.text}", 'cross'),
                        ephemeral=True
                    )
                    return None
            elif e.status == 429:
                logger.warning(
                    "TicketModal.ticket_thread_constructor: rate limited creating ticket channel in guild %s",
                    interaction.guild.id
                )
                await interaction.followup.send(
                    embed=simple_embed("Discord is rate-limiting requests right now, please try again shortly.", 'cross'),
                    ephemeral=True
                )
                return None
            else:
                logger.exception(
                    "TicketModal.ticket_thread_constructor: HTTP error creating ticket channel in guild %s",
                    interaction.guild.id
                )
                await interaction.followup.send(
                    embed=simple_embed("Failed to create the ticket channel due to a Discord API error!", 'cross'),
                    ephemeral=True
                )
                return None

        if not isinstance(opener, discord.Member):
            logger.error(
                "TicketModal.ticket_thread_constructor: opener %s is not a Member instance in guild %s",
                getattr(opener, "id", "unknown"), interaction.guild.id
            )
            return

        opener_view = TicketOpenerComponent(submission_json=submission_json, ticket_channel_id=text_channel.id)
        view = TicketComponentEmbed(ticket_channel_id=text_channel.id, submission_json=submission_json)

        try:
            ticket_message: discord.Message = await text_channel.send(view=opener_view)
            ticket_details_thread = await ticket_message.create_thread(
                name="Ticket Details"
            )

            ticket_details_message: discord.Message = await ticket_details_thread.send(
                view=view,
                allowed_mentions=discord.AllowedMentions.none()
            )
        except discord.HTTPException:
            logger.exception(
                "TicketModal.ticket_thread_constructor: failed to send ticket messages/thread in channel %s",
                text_channel.id
            )
            await interaction.followup.send(
                embed=simple_embed("Failed to fully set up the ticket channel due to a network error!", 'cross'),
                ephemeral=True
            )
            return None

        try:
            await ticket_message.pin()
        except discord.Forbidden:
            logger.exception(
                "TicketModal.ticket_thread_constructor: missing permissions to pin ticket message %s",
                ticket_message.id
            )
        except discord.HTTPException:
            logger.exception(
                "TicketModal.ticket_thread_constructor: HTTP error pinning ticket message %s",
                ticket_message.id
            )

        if proofs_flag:
            try:
                await text_channel.send(content=f"{proof_url}")
            except discord.HTTPException:
                logger.exception(
                    "TicketModal.ticket_thread_constructor: failed to send proofs in channel %s",
                    text_channel.id
                )

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        try:
            await bot_db.create_ticket(
                text_channel.id,
                interaction.guild.id,
                opener.id,
                ticket_name_base,
                logging_channel_id,
                submission_json,
                ticket_message.id,
                ticket_details_message.id
            )
        except Exception:
            logger.exception(
                "TicketModal.ticket_thread_constructor: create_ticket db call failed for channel %s",
                text_channel.id
            )
        return text_channel

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return

        await interaction.response.defer(ephemeral=True)

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        try:
            tickets = await bot_db.get_ticket_by_opener(interaction.user.id, interaction.guild.id)
        except Exception:
            logger.exception(
                "TicketModal.on_submit: get_ticket_by_opener failed for user %s in guild %s",
                interaction.user.id, interaction.guild.id
            )
            await interaction.followup.send(
                embed=simple_embed("Failed to check your existing tickets due to a database error!", 'cross'),
                ephemeral=True
            )
            return

        if len(tickets) >= 3:
            references = ", ".join(f"<#{t.id}>" for t in tickets)
            await interaction.followup.send(
                embed=simple_embed(
                    "Your ticket cannot be created.\n"
                    "Please close your previous tickets first.\n"
                    f"**References:** {references}"
                ),
                ephemeral=True
            )
            return

        try:
            ticket_view = await bot_db.get_ticket_view(view_id=self.view_id)
        except Exception:
            logger.exception(
                "TicketModal.on_submit: failed to load ticket configuration for panel %s",
                self.view_id
            )
            await interaction.followup.send(
                embed=simple_embed("Failed to load the ticket configuration due to a database error!", 'cross'),
                ephemeral=True
            )
            return

        if ticket_view is None or ticket_view.logging_channel_id is None:
            await interaction.followup.send(
                embed=simple_embed("This ticket panel is no longer configured. Please contact an admin.", 'cross'),
                ephemeral=True
            )
            return

        higher_staff_role_ids = ticket_view.staff_role_ids
        logs_channel_id = ticket_view.logging_channel_id

        channel_id = self.ticket.channel_id
        ticket_name_base = self.ticket.ticket_base_name
        channel_emoji = self.ticket.channel_emoji or ""
        ping_roles = self.ticket.ping_roles

        field_data: List[Dict] = []

        bot: commands.Bot = cast(commands.Bot, interaction.client)

        try:
            ctx = await bot.get_context(self.message)
        except Exception:
            logger.exception(
                "TicketModal.on_submit: get_context failed for message %s",
                self.message.id
            )
            await interaction.followup.send(
                embed=simple_embed("Failed to prepare the ticket submission due to an unexpected error!", 'cross'),
                ephemeral=True
            )
            return

        for data in self.components:
            field = data["field"]
            item = data["item"]

            field_type = field["type"]

            if field_type == "file_upload":
                assert isinstance(item.component, discord.ui.FileUpload)
                field_data.append({
                    "field": field,
                    "value": [attachment.url for attachment in item.component.values]
                })
            
            elif field_type == "member":
                assert isinstance(item.component, discord.ui.TextInput)
                # Try fetching the member details.
                try:
                    user = re.sub(r"[^\w.]", "", str(item.component.value).lstrip("@")).lower()

                    member: discord.Member = await self.converter.convert(
                        ctx,
                        user
                    )

                    field_data.append({
                        "field": field,
                        "value": {
                            "flag": 0,
                            "username": member.global_name,
                            "member_id": member.id,
                            "avatar": member.display_avatar.url,
                            "created_on": f"<t:{int(member.created_at.timestamp())}:R>",
                            "joined_on": f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "<t:0:R>",
                        }
                    })
                except Exception:
                    logger.warning(
                        "TicketModal.on_submit: could not resolve member field value %r, falling back to raw text",
                        item.component.value,
                        exc_info=True
                    )
                    field_data.append({
                        "field": field,
                        "value": {
                            "flag": 1,
                            "username": item.component.value
                        }
                    })

                ...

            elif field_type == "guild_invite":
                assert isinstance(item.component, discord.ui.TextInput)
                client = interaction.client

                try:
                    invite = await client.fetch_invite(item.component.value)
                    guild = invite.guild

                    if guild is None or isinstance(guild, discord.Object):
                        field_data.append({
                            "field": field,
                            "value": {
                                "flag": 1,
                                "invite_url": item.component.value
                            }
                        })

                    else:
                        field_data.append({
                            "field": field,
                            "value": {
                                "flag": 0,
                                "name": guild.name,
                                "icon": guild.icon.url if guild.icon else None,
                                "member_count": invite.approximate_member_count,
                                "owner_id": guild.owner_id if isinstance(guild, discord.Guild) else 0,
                                "invite_url": f"https://discord.com/invite/{invite.code}",
                            }
                        })
                except Exception:
                    logger.warning(
                        "TicketModal.on_submit: could not resolve guild invite field value %r, falling back to raw text",
                        item.component.value,
                        exc_info=True
                    )
                    field_data.append({
                        "field": field,
                        "value": {
                            "flag": 0,
                            "invite_url": item.component.value
                        }
                    })


            elif field_type == "role_select":
                assert isinstance(item.component, discord.ui.RoleSelect)
                field_data.append({
                    "field": field,
                    "value": [role.name for role in item.component.values]
                })

            elif field_type == "selector":
                assert isinstance(item.component, discord.ui.Select)
                field_data.append({
                    "field": field,
                    "value": [str(v) for v in item.component.values]
                })

            elif field_type == "radio_option":
                assert isinstance(item.component, discord.ui.RadioGroup)
                chosen = item.component.value
                field_data.append({
                    "field": field,
                    "value": [str(chosen)] if chosen else []
                })

            elif field_type == "check_box":
                if isinstance(item.component, discord.ui.Checkbox):
                    only_option = self.parse_field_options(field)[:1]
                    field_data.append({
                        "field": field,
                        "value": only_option if item.component.value else []
                    })
                else:
                    assert isinstance(item.component, discord.ui.CheckboxGroup)
                    field_data.append({
                        "field": field,
                        "value": [str(v) for v in item.component.values]
                    })

            else:
                assert isinstance(item.component, discord.ui.TextInput)
                field_data.append({
                    "field": field,
                    "value": item.component.value
                })

        assert isinstance(interaction.user, discord.Member)
        opener_details = {
            "username": interaction.user.global_name,
            "member_id": interaction.user.id,
            "avatar": interaction.user.display_avatar.url,
            "created_on": f"<t:{int(interaction.user.created_at.timestamp())}:R>",
            "joined_on": f"<t:{int(interaction.user.joined_at.timestamp())}:R>" if interaction.user.joined_at else "<t:0:R>",
        }

        submission = {
            "opener": opener_details,
            "channel_id": channel_id,
            "message_id": ctx.message.id,
            "fields": self.fields,
            "field_data": field_data,
            "ticket_name_base": ticket_name_base,
            "channel_emoji": channel_emoji,
            "logs_channel_id" : logs_channel_id,
            "ping_roles" : ping_roles
        }

        try:
            thread_channel: discord.TextChannel | discord.Thread | None = await self.ticket_thread_constructor(
                interaction,
                submission,
                logs_channel_id,
                higher_staff_role_ids
            )
        except Exception:
            logger.exception(
                "TicketModal.on_submit: ticket_thread_constructor raised for user %s in guild %s",
                interaction.user.id, interaction.guild.id
            )
            await interaction.followup.send(
                embed=simple_embed("Failed to create your ticket due to an unexpected error!", 'cross'),
                ephemeral=True
            )
            return

        if thread_channel is not None:
            try:
                await interaction.followup.send(
                    embed=simple_embed(
                        f"Your ticket has been created: {thread_channel.mention}"
                    ),
                    ephemeral=True
                )
            except discord.HTTPException:
                logger.exception(
                    "TicketModal.on_submit: failed to send ticket-created confirmation for channel %s",
                    thread_channel.id
                )

class TicketSelectComponent(discord.ui.LayoutView):
    CUSTOM_ID = "ticket_selector_main"

    def __init__(self, panel: TicketPanel | None, ticket_types: Sequence[TicketType]) -> None:
        super().__init__(timeout=None)

        if not ticket_types:
            raise ValueError("A ticket panel needs at least one ticket type.")

        self.ticket_options = discord.ui.Select(
            placeholder="Choose a ticket type...",
            custom_id=self.CUSTOM_ID,
            options=[
                discord.SelectOption(
                    label=ticket.label,
                    emoji=ticket.emoji or None,
                    description=ticket.description or None,
                    value=ticket.ticket_base_name,
                )
                for ticket in ticket_types
            ],
        )
        self.ticket_options.callback = self.ticket_selector_callback

        title = (panel.title if panel else None) or "Support Tickets"
        description = (panel.description if panel else None) or "Select a ticket type below to get started."
        thumbnail_url = panel.thumbnail_url if panel else None

        if thumbnail_url:
            header = [
                discord.ui.Section(
                    discord.ui.TextDisplay(content=f"## {title}"),
                    discord.ui.TextDisplay(content=description),
                    accessory=discord.ui.Thumbnail(media=thumbnail_url),
                )
            ]
        else:
            header = [
                discord.ui.TextDisplay(content=f"## {title}"),
                discord.ui.TextDisplay(content=description),
            ]

        children: list[discord.ui.Item] = [
            *header, 
            discord.ui.ActionRow(self.ticket_options)
        ]
        footer = panel.footer_text if panel else None
        if footer:
            children.append(discord.ui.TextDisplay(content=f"-# {footer}"))

        self.add_item(discord.ui.Container(*children))

    @classmethod
    async def from_db(cls, bot_db: BotGlobalsDatabaseAccess, view_id: int) -> "TicketSelectComponent":
        """Build the panel from the normalized tables (restart / refresh path)."""
        view = await bot_db.get_ticket_view(view_id=view_id)
        if view is None:
            raise ValueError(f"Ticket panel {view_id} does not exist.")
        return cls(view.panel, view.types)

    @classmethod
    def from_config(cls, config: dict) -> "TicketSelectComponent":
        """
        Only for spawning a brand-new panel: the row cannot be saved before the
        message exists (message_id is NOT NULL), so the first render comes from
        the config that is about to be saved.
        """
        panel_config = config.get("PanelConfig") or {}
        panel = TicketPanel(
            title=panel_config.get("title"),
            description=panel_config.get("description"),
            footer_text=(panel_config.get("footer") or {}).get("text"),
            thumbnail_url=(panel_config.get("thumbnail") or {}).get("url"),
        )
        ticket_types = [
            TicketType(
                id=0,
                label=ticket["label"],
                ticket_base_name=ticket["ticket_base_name"],
                description=ticket.get("description"),
                emoji=ticket.get("emoji"),
            )
            for ticket in config.get("Tickets") or []
        ]
        return cls(panel, ticket_types)

    async def ticket_selector_callback(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.message is None:
            return

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None

        selected = self.ticket_options.values[0]

        try:
            ticket_view = await bot_db.get_ticket_view(
                message_id=interaction.message.id, guild_id=interaction.guild.id
            )
        except Exception:
            logger.exception(
                "TicketSelectComponent.ticket_selector_callback: failed to load ticket type %r for message %s",
                selected, interaction.message.id
            )
            await interaction.response.send_message(
                embed=simple_embed("Failed to load this ticket type due to a database error!", 'cross'),
                ephemeral=True
            )
            return

        if ticket_view is None:
            await interaction.response.send_message(
                embed=simple_embed("This ticket panel is no longer configured!", 'cross'),
                ephemeral=True
            )
            return

        ticket = ticket_view.get_type(selected)

        if ticket is None:
            logger.warning(
                "TicketSelectComponent.ticket_selector_callback: ticket type %r no longer exists on panel %s",
                selected, ticket_view.id
            )
            await interaction.response.send_message(
                embed=simple_embed("That ticket type is no longer available!", 'cross'),
                ephemeral=True
            )
            return

        try:
            modal = TicketModal(
                title=ticket.label,
                ticket=ticket,
                view_id=ticket_view.id,
                message=interaction.message
            )
        except (TypeError, ValueError):
            logger.exception(
                "TicketSelectComponent.ticket_selector_callback: failed to build TicketModal for ticket %r",
                ticket.label
            )
            await interaction.response.send_message(
                embed=simple_embed("This ticket type is misconfigured. Please contact an admin.", 'cross'),
                ephemeral=True
            )
            return

        try:
            await interaction.response.send_modal(modal)
        except discord.HTTPException:
            logger.exception(
                "TicketSelectComponent.ticket_selector_callback: failed to send ticket modal for ticket %r",
                ticket.label
            )

class TicketLogComponent(discord.ui.LayoutView):
    def __init__(self, ticket_opener: int, ticket_closed_by: int ,ticket_type: str, reason: str, transcript_file_name: str) -> None:
        super().__init__(timeout=10)    

        container = discord.ui.Container(
            discord.ui.TextDisplay(content=f"# Ticket Log | {ticket_type}"),
            discord.ui.TextDisplay(content=f"### Ticket Opener\n- <@{ticket_opener}>"),
            discord.ui.TextDisplay(content=f"### Ticket Closed by\n- <@{ticket_closed_by}>"),
            discord.ui.TextDisplay(content=f"### Reason\n- {reason}"),
            discord.ui.TextDisplay(content="### Ticket Transcripts"),
            discord.ui.File(
                media=f"attachment://{transcript_file_name}",
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        )

        self.add_item(container)

class TicketLogDirectMessage(discord.ui.LayoutView):
    def __init__(self, ticket_type: str, ticket_closed_by: int, reason: str, server_name: str, transcript_file_name: str):

        super().__init__(timeout=10)

        container = discord.ui.Container(
            discord.ui.TextDisplay(content=f"## Ticket Closed | {ticket_type}"),
            discord.ui.TextDisplay(content=f"### Handled by\n- <@{ticket_closed_by}>"),
            discord.ui.TextDisplay(content=f"### Reason\n- {reason}"),
            discord.ui.TextDisplay(content=f"### Server\n- {server_name}"),
            discord.ui.TextDisplay(content="### Transcript"),
            discord.ui.File(
                media=f"attachment://{transcript_file_name}",
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        )

        self.add_item(container)

class TicketList(discord.ui.LayoutView):
    def __init__(
        self,
        ticket_result: Page[TicketLog],
        ticket_types: List[str],
        *,
        opened_user_id: int | None = None,
        staff_handled: int | None = None,
        ticket_type: str | None = None,
        guild_avatar: str | None = None
    ) -> None:
        super().__init__(timeout=None)

        self.page = ticket_result.page
        self.max_page = ticket_result.max_page
        self.total_count = ticket_result.total_count
        self.ticket_types = ticket_types
        self.opened_user_id = opened_user_id
        self.staff_handled = staff_handled
        self.ticket_type = ticket_type
        self.guild_avatar: str | None = guild_avatar

        self.ticket_results: list[TicketLog] = ticket_result.items
        self.ticket_sections: List[discord.ui.Section] = []

        for log in self.ticket_results:
            retrieve_ticket = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji=emoji["paper_clip"],
                custom_id=str(log.id),
            )
    
            retrieve_ticket.callback = self.retrieve_ticket_callback

            type_label = (log.ticket_type or "unknown").replace("_", " ").title()
            staff_label = f"<@{log.staff_handled}>" if log.staff_handled else "*Unassigned*"

            self.ticket_sections.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=f"### {type_label} | <@{log.opened_user_id}>"
                    ),
                    discord.ui.TextDisplay(
                        content=f"- {emoji['staff']} Staff Handled: {staff_label}\n- {emoji['clock']} Timestamp: {_discord_ts(log.opened_at)}"
                    ),
                    accessory=retrieve_ticket
                )
            )

        self.prev_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["left"],
            disabled=not ticket_result.has_prev,
        )
        self.prev_button.callback = self.on_prev

        self.page_indicator = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=f"{self.page} / {self.max_page}",
            disabled=True,
        )

        self.next_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["right"],
            disabled=not ticket_result.has_next,
        )
        self.next_button.callback = self.on_next

        self.container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content="## Ticket Logs"),
                discord.ui.TextDisplay(content="- Displaying All Ticket Logs Available on this server."),
                discord.ui.TextDisplay(content=f"- Total Tickets: {self.total_count}"),
                accessory=discord.ui.Thumbnail(
                    media=guild_avatar or (
                        "https://media.discordapp.net/attachments/1510416807847133274/1518277154889269248/Kaede.png?ex=6a93a409&is=6a925289&hm=3daa457e8c1924deb10c3b367bad064bd538b61ab408b5cb77629864a8aca4d3&=&format=webp&quality=lossless"
                    ),
                ),
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            *self.ticket_sections,
            discord.ui.ActionRow(self.prev_button, self.page_indicator, self.next_button),
        )

        self.user_select = discord.ui.UserSelect(
            placeholder="Filter based on Ticket Opener",
            min_values=0,
            max_values=1
        )

        self.user_select.callback = self.default_selector_callback

        self.staff_select = discord.ui.UserSelect(
            placeholder="Filter based on Staffs Handled",
            min_values=0,
            max_values=1
        )

        self.staff_select.callback = self.default_selector_callback


        type_options = [
            discord.SelectOption(label="All Types", value="__all__", default=self.ticket_type is None)
        ]
        for t in self.ticket_types:
            type_options.append(
                discord.SelectOption(
                    label=t.replace("_", " ").title(),
                    value=t,
                    default=t == self.ticket_type,
                )
            )

        self.ticket_type_select = discord.ui.Select(
            placeholder="Filter based on Ticket Type",
            min_values=1,
            max_values=1,
            options=type_options,
        )

        self.ticket_type_select.callback = self.default_selector_callback

        self.apply_filter_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Apply Filter"
        )
        self.apply_filter_btn.callback = self.on_apply_filter

        self.filter_container = discord.ui.Container(
            discord.ui.TextDisplay(content="### Ticket Filters"),
            discord.ui.ActionRow(
                self.user_select
            ),
            discord.ui.ActionRow(
                self.staff_select
            ),
            discord.ui.ActionRow(
                self.ticket_type_select
            ),
            discord.ui.ActionRow(
                self.apply_filter_btn
            )
        )

        self.add_item(self.container)
        self.add_item(self.filter_container)

    async def on_prev(self, interaction: discord.Interaction) -> None:
        self.page -= 1
        await self.refresh(interaction)

    async def on_next(self, interaction: discord.Interaction) -> None:
        self.page += 1
        await self.refresh(interaction)

    async def default_selector_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(content=f"{emoji["verified"]}", ephemeral=True)

    async def retrieve_ticket_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.data is not None
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        assert interaction.custom_id is not None
        assert interaction.guild is not None
        ticket_id = int(interaction.custom_id)

        try:
            result = await bot_db.get_ticket_log(
                ticket_id,
                interaction.guild.id
            )
        except Exception:
            logger.exception(
                "TicketList.retrieve_ticket_callback: get_ticket_log failed for ticket %s in guild %s",
                ticket_id, interaction.guild.id
            )
            await interaction.response.send_message(
                f"Failed to retrieve ticket #{ticket_id} due to a database error.",
                ephemeral=True,
            )
            return

        if result is None:
            await interaction.response.send_message(
                f"Ticket #{ticket_id} could not be found.",
                ephemeral=True,
            )
            return

        type_label = (result.ticket_type or "unknown").replace("_", " ").title()
        reason = result.reason or "*No reason provided*"

        container_items: list[discord.ui.Item] = [
            discord.ui.Section(
                discord.ui.TextDisplay(content="## Ticket Information"),
                discord.ui.TextDisplay(content=f"- Showing ticket information for #{ticket_id}"),
                accessory=discord.ui.Thumbnail(
                    media=interaction.guild.icon.url if interaction.guild.icon else interaction.guild.me.display_avatar.url,
                ),
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content=f"### Opened By\n- <@{result.opened_user_id}>"),
            discord.ui.TextDisplay(content=f"### Staff Handled\n- <@{result.staff_handled}>" if result.staff_handled else "*Unassigned*"),
            discord.ui.TextDisplay(content=f"### Ticket Type\n- {type_label}"),
            discord.ui.TextDisplay(content=f"### Timestamp\n- {_discord_ts(result.opened_at)}"),
            discord.ui.TextDisplay(content=f"### Reason\n- {reason}"),
        ]

        if result.logs_channel_id and result.transcripts_reference:
            container_items.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(content="### Transcript Reference"),
                    accessory=discord.ui.Button(
                        url=f"https://discord.com/channels/{interaction.guild.id}/{result.logs_channel_id}/{result.transcripts_reference}",
                        style=discord.ButtonStyle.link,
                        label="Transcript"
                    ),
                )
            )

        view = discord.ui.LayoutView().add_item(discord.ui.Container(*container_items))

        try:
            await interaction.response.send_message(view=view, ephemeral=True)
        except discord.HTTPException:
            logger.exception(
                "TicketList.retrieve_ticket_callback: failed to send ticket info for ticket %s",
                ticket_id
            )

    async def on_apply_filter(self, interaction: discord.Interaction) -> None:
        self.opened_user_id = self.user_select.values[0].id if self.user_select.values else None
        self.staff_handled = self.staff_select.values[0].id if self.staff_select.values else None
        chosen_type = self.ticket_type_select.values[0] if self.ticket_type_select.values else "__all__"
        self.ticket_type = None if chosen_type == "__all__" else chosen_type
        self.page = 1
        await self.refresh(interaction)

    async def refresh(self, interaction: discord.Interaction) -> None:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        assert interaction.guild is not None

        try:
            ticket_result = await bot_db.get_ticket_logs(
                interaction.guild.id,
                opened_user_id=self.opened_user_id,
                staff_handled=self.staff_handled,
                ticket_type=self.ticket_type,
                page=self.page,
            )
        except Exception:
            logger.exception(
                "TicketList.refresh: get_ticket_logs failed for guild %s (page %s)",
                interaction.guild.id, self.page
            )
            await interaction.response.send_message(
                embed=simple_embed("Failed to refresh ticket logs due to a database error!", 'cross'),
                ephemeral=True
            )
            return

        guild_avatar = interaction.guild.icon.url if interaction.guild.icon else None
        new_view = TicketList(
            ticket_result,
            self.ticket_types,
            opened_user_id=self.opened_user_id,
            staff_handled=self.staff_handled,
            ticket_type=self.ticket_type,
            guild_avatar=guild_avatar
        )

        try:
            await interaction.response.edit_message(view=new_view)
        except discord.HTTPException:
            logger.exception(
                "TicketList.refresh: failed to edit message with refreshed ticket list for guild %s",
                interaction.guild.id
            )


# Ticket Dashboard
       
TICKET_MODES = {"channel": "Channel", "thread": "Thread"}
BASE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
FIELD_TYPES = {
    "short": ("Short text", "Accepts a short text response."),
    "long": ("Long text", "Accepts a longer, multi-line text response."),
    "member": ("Member", "Resolves a Discord member object for member-specific actions."),
    "guild_invite": ("Server invite", "Accepts a Discord server invite link."),
    "file_upload": ("File upload", "Allows users to upload files as attachments."),
    "role_select": ("Role select", "Allows users to select a role from the server."),
    "selector": ("Select Options", "Allows users to choose one or more predefined options."),
    "radio_option": ("Radio Options", "Allows users to select a single option from predefined choices."),
    "check_box": ("Checkbox", "Allows users to toggle a predefined option on or off.")
}
TEXT_FIELD_TYPES = {"short", "long", "member", "guild_invite"}
DEFAULT_FIELDS = [{"label": "Describe your issue", "type": "long", "length": 500}]

OPTION_FIELD_TYPES = {"selector", "radio_option", "check_box"}
MAX_SELECT_OPTIONS = 25
MAX_RADIO_OPTIONS = 10


def get_db(interaction: discord.Interaction):
    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None
    return bot_db

async def edit_view(interaction: discord.Interaction, view: discord.ui.LayoutView) -> None:
    if interaction.response.is_done():
        await interaction.edit_original_response(view=view, allowed_mentions=discord.AllowedMentions.none())
    else:
        await interaction.response.edit_message(view=view, allowed_mentions=discord.AllowedMentions.none())

def page_slice(items: list, page: int, size: int = 5):
    max_page = max(1, ceil(len(items) / size))
    page = min(max(1, page), max_page)
    return items[(page - 1) * size : page * size], page, max_page

def channel_defaults(channel_id: int | None) -> list[discord.SelectDefaultValue]:
    if not channel_id:
        return []
    return [discord.SelectDefaultValue(id=channel_id, type=discord.SelectDefaultValueType.channel)]

def role_defaults(role_ids) -> list[discord.SelectDefaultValue]:
    return [
        discord.SelectDefaultValue(id=r, type=discord.SelectDefaultValueType.role)
        for r in list(role_ids)[:25]
    ]

def ticket_type_to_dict(t: TicketType) -> dict[str, Any]:
    return {
        "label": t.label,
        "description": t.description,
        "emoji": t.emoji,
        "channel_id": t.channel_id,
        "channel_emoji": t.channel_emoji,
        "ticket_base_name": t.ticket_base_name,
        "fields": list(t.fields),
        "ping_roles": list(t.ping_roles),
    }

def view_to_config(tv: TicketView) -> dict[str, Any]:
    panel = tv.panel
    return {
        "BasicConfigurations": {
            "TicketPanelSpawnChannel": tv.spawn_channel_id,
            "TicketLoggingHandler": tv.logging_channel_id,
            "TicketType": tv.ticket_type,
            "higher_staffs_role_id": list(tv.staff_role_ids),
        },
        "PanelConfig": (
            {
                "title": panel.title,
                "description": panel.description,
                "footer": {"text": panel.footer_text},
                "thumbnail": {"url": panel.thumbnail_url},
            }
            if panel
            else {}
        ),
        "Tickets": [ticket_type_to_dict(t) for t in tv.types],
    }

def find_ticket(config: dict[str, Any], base_name: str) -> dict[str, Any]:
    for entry in config["Tickets"]:
        if entry["ticket_base_name"] == base_name:
            return entry
    raise LilyError("Ticket type not found.")

def build_panel_view(tv: TicketView) -> discord.ui.LayoutView:
    return TicketSelectComponent(tv.panel, tv.types)

async def sync_panel_message(guild: discord.Guild, tv: TicketView) -> str | None:
    try:
        channel = guild.get_channel(tv.channel_id) or await guild.fetch_channel(tv.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return "the panel channel is no longer a text channel."
        message = await channel.fetch_message(tv.message_id)
        await message.edit(view=build_panel_view(tv))
    except discord.NotFound:
        return "the posted panel message no longer exists."
    except discord.Forbidden:
        return "I don't have permission to edit the posted panel message."
    except discord.HTTPException:
        logger.exception("Failed to edit ticket panel message (view_id=%s)", tv.id)
        return "Discord rejected the panel update (check emojis and image URLs)."
    return None

async def delete_panel_message(guild: discord.Guild, tv: TicketView) -> None:
    with suppress(discord.HTTPException):
        channel = guild.get_channel(tv.channel_id) or await guild.fetch_channel(tv.channel_id)
        if isinstance(channel, discord.TextChannel):
            await channel.get_partial_message(tv.message_id).delete()

async def save_changes(
    interaction: discord.Interaction,
    tv: TicketView,
    mutate: Callable[[dict[str, Any]], None],
) -> TicketView | None:
    assert interaction.guild is not None
    bot_db = get_db(interaction)

    try:
        latest = await bot_db.get_ticket_view(view_id=tv.id)
        if latest is None:
            raise LilyError("This ticket panel no longer exists.")

        config = view_to_config(latest)
        mutate(config)
        new_tv = await bot_db.save_ticket_view(latest.guild_id, latest.channel_id, latest.message_id, config)
    except LilyError as exc:
        await interaction.followup.send(embed=simple_embed(str(exc), "cross"), ephemeral=True)
        return None
    except Exception:
        logger.exception("Failed to save ticket panel (view_id=%s)", tv.id)
        await interaction.followup.send(
            embed=simple_embed("Failed to save the ticket panel. Please try again later.", "cross"),
            ephemeral=True,
        )
        return None

    problem = await sync_panel_message(interaction.guild, new_tv)
    if problem:
        await interaction.followup.send(
            embed=simple_embed(f"Saved, but the panel message wasn't updated: {problem}", "cross"),
            ephemeral=True,
        )
    return new_tv

class TicketPanelList(discord.ui.LayoutView):
    def __init__(self, guild_id: int, panels: list[TicketView], page: int = 1) -> None:
        super().__init__(timeout=None)

        self.guild_id = guild_id
        self.panels = panels
        self.shown, self.page, self.max_page = page_slice(panels, page)

        items: List[discord.ui.Item] = []
        for tv in self.shown:
            edit_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Edit",
            )
            edit_button.callback = self._edit_callback(tv.id)

            title = (tv.panel.title if tv.panel else None) or "Untitled panel"
            items.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=f"**#{tv.id}** {title}\n-# <#{tv.channel_id}> | {len(tv.types)} ticket type(s)"
                    ),
                    accessory=edit_button,
                )
            )

        if not items:
            items.append(discord.ui.TextDisplay(content="*No ticket panels yet.*"))

        prev_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji=emoji["left"], disabled=self.page <= 1
        )
        prev_button.callback = self.previous_callback

        page_indicator: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=f"Page {self.page}/{self.max_page}",
            disabled=True,
        )

        next_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji=emoji["right"], disabled=self.page >= self.max_page
        )
        next_button.callback = self.next_callback

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(content="### Ticket Panels\n- Create and manage ticket panels"),
                discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                *items,
                discord.ui.ActionRow(prev_button, page_indicator, next_button),
            )
        )

        add_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="Add", emoji=emoji["plus"]
        )
        add_button.callback = self.add_callback

        remove_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Remove",
            emoji=emoji["trash"],
            disabled=not self.shown,
        )
        remove_button.callback = self.remove_callback

        self.add_item(discord.ui.ActionRow(add_button, remove_button))

    @classmethod
    async def create(cls, bot_db, guild_id: int, page: int = 1) -> "TicketPanelList":
        return cls(guild_id, await bot_db.get_ticket_views(guild_id), page)

    async def refresh(self, interaction: discord.Interaction, page: int) -> None:
        view = await TicketPanelList.create(get_db(interaction), self.guild_id, page)
        await edit_view(interaction, view)

    async def previous_callback(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction, self.page - 1)

    async def next_callback(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction, self.page + 1)

    async def add_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddPanelModal(self))

    async def remove_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RemovePanelModal(self))

    def _edit_callback(self, view_id: int):
        async def callback(interaction: discord.Interaction) -> None:
            tv = await get_db(interaction).get_ticket_view(view_id=view_id)
            if tv is None:
                await interaction.response.send_message(
                    embed=simple_embed("Ticket panel not found", "cross"), ephemeral=True
                )
                return
            await edit_view(interaction, TicketPanelEdit(self, tv))

        return callback

class AddPanelModal(discord.ui.Modal):
    def __init__(self, list_view: TicketPanelList) -> None:
        super().__init__(title="Add Ticket Panel")
        self.list_view = list_view

        self.title_input = discord.ui.TextInput(label="Panel Title", max_length=256, default="Support")
        self.description_input = discord.ui.TextInput(
            label="Panel Description",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=4000,
        )
        self.spawn_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            placeholder="Channel to post the panel in",
            min_values=1,
            max_values=1,
        )
        self.log_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            placeholder="Channel for ticket logs",
            min_values=1,
            max_values=1,
        )
        self.mode_select = discord.ui.Select(
            placeholder="How tickets are created",
            options=[discord.SelectOption(label=name, value=key) for key, name in TICKET_MODES.items()],
        )

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(discord.ui.Label(text="Panel Channel", component=self.spawn_select))
        self.add_item(discord.ui.Label(text="Logging Channel", component=self.log_select))
        self.add_item(discord.ui.Label(text="Ticket Mode", component=self.mode_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        guild = interaction.guild
        bot_db = get_db(interaction)

        spawn = guild.get_channel(self.spawn_select.values[0].id)
        if not isinstance(spawn, discord.TextChannel):
            await interaction.response.send_message(
                embed=simple_embed("Pick a text channel for the panel.", "cross"), ephemeral=True
            )
            return

        perms = spawn.permissions_for(guild.me)
        if not (perms.view_channel and perms.send_messages):
            await interaction.response.send_message(
                embed=simple_embed(f"I can't send messages in {spawn.mention}.", "cross"), ephemeral=True
            )
            return

        await interaction.response.defer()

        placeholder = discord.ui.LayoutView(timeout=None)
        placeholder.add_item(discord.ui.TextDisplay(content="*Setting up ticket panel...*"))
        try:
            message = await spawn.send(view=placeholder)
        except discord.HTTPException:
            logger.exception("Failed to post ticket panel (guild_id=%s)", guild.id)
            await interaction.followup.send(
                embed=simple_embed("Couldn't post the panel message.", "cross"), ephemeral=True
            )
            return

        config = {
            "BasicConfigurations": {
                "TicketPanelSpawnChannel": spawn.id,
                "TicketLoggingHandler": self.log_select.values[0].id,
                "TicketType": self.mode_select.values[0],
                "higher_staffs_role_id": [],
            },
            "PanelConfig": {
                "title": self.title_input.value,
                "description": self.description_input.value or None,
                "footer": {},
                "thumbnail": {},
            },
            "Tickets": [
                {
                    "label": "General Support",
                    "description": "Open a general support ticket",
                    "ticket_base_name": "support",
                    "fields": [dict(f) for f in DEFAULT_FIELDS],
                    "ping_roles": [],
                }
            ],
        }

        try:
            tv = await bot_db.save_ticket_view(guild.id, spawn.id, message.id, config)
        except Exception as exc:
            logger.exception("Failed to save new ticket panel (guild_id=%s)", guild.id)
            with suppress(discord.HTTPException):
                await message.delete()
            text = str(exc) if isinstance(exc, LilyError) else "Failed to save the ticket panel."
            await interaction.followup.send(embed=simple_embed(text, "cross"), ephemeral=True)
            return

        problem = await sync_panel_message(guild, tv)
        if problem:
            await interaction.followup.send(
                embed=simple_embed(f"Panel saved, but couldn't render it: {problem}", "cross"),
                ephemeral=True,
            )

        await edit_view(interaction, TicketPanelEdit(self.list_view, tv))

class RemovePanelModal(discord.ui.Modal):
    def __init__(self, list_view: TicketPanelList) -> None:
        super().__init__(title="Remove Ticket Panel")
        self.list_view = list_view

        self.select = discord.ui.Select(
            placeholder="Select a panel",
            options=[
                discord.SelectOption(
                    label=f"#{tv.id} {(tv.panel.title if tv.panel else None) or 'Untitled panel'}"[:100],
                    value=str(tv.id),
                )
                for tv in list_view.shown
            ],
        )
        self.add_item(discord.ui.Label(text="Panel to remove", component=self.select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        view_id = int(self.select.values[0])
        tv = next((p for p in self.list_view.shown if p.id == view_id), None)
        if tv is None:
            await self.list_view.refresh(interaction, self.list_view.page)
            return

        await interaction.response.edit_message(view=TicketPanelDeleteConfirm(self.list_view, tv))

class TicketPanelDeleteConfirm(discord.ui.LayoutView):
    def __init__(self, list_view: TicketPanelList, tv: TicketView) -> None:
        super().__init__(timeout=300)
        self.list_view = list_view
        self.tv = tv

        delete_button: discord.ui.Button = discord.ui.Button(style=discord.ButtonStyle.danger, label="Delete")
        delete_button.callback = self.delete_callback

        cancel_button: discord.ui.Button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Cancel")
        cancel_button.callback = self.cancel_callback

        title = (tv.panel.title if tv.panel else None) or "Untitled panel"
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    content=(
                        f"### Delete #{tv.id} {title}?\n"
                        f"This deletes the panel configuration and its **{len(tv.types)}** ticket type(s), "
                        f"and removes the posted panel message. This cannot be undone.\n"
                        f"-# Open tickets from this panel stay, but staff can no longer claim them or use their moderation buttons."
                    )
                ),
                discord.ui.ActionRow(delete_button, cancel_button),
            )
        )

    async def delete_callback(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer()

        try:
            await get_db(interaction).delete_ticket_view(self.tv.message_id)
        except LilyError:
            pass  # already gone
        except Exception:
            logger.exception("Failed to delete ticket panel (view_id=%s)", self.tv.id)
            await interaction.followup.send(
                embed=simple_embed("Failed to delete the ticket panel.", "cross"), ephemeral=True
            )
            return

        await delete_panel_message(interaction.guild, self.tv)
        await self.list_view.refresh(interaction, self.list_view.page)

    async def cancel_callback(self, interaction: discord.Interaction) -> None:
        await self.list_view.refresh(interaction, self.list_view.page)

class TicketPanelEdit(discord.ui.LayoutView):
    def __init__(self, list_view: TicketPanelList, tv: TicketView, page: int = 1) -> None:
        super().__init__(timeout=None)

        self.list_view = list_view
        self.tv = tv
        shown, self.page, self.max_page = page_slice(tv.types, page)

        title = (tv.panel.title if tv.panel else None) or "Untitled panel"
        staff = " ".join(f"<@&{r}>" for r in tv.staff_role_ids) or "*None*"
        logging_text = f"<#{tv.logging_channel_id}>" if tv.logging_channel_id else "*Not set*"
        jump = f"https://discord.com/channels/{tv.guild_id}/{tv.channel_id}/{tv.message_id}"

        back_button: discord.ui.Button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Back")
        back_button.callback = self.back_callback

        appearance_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="Appearance", emoji=emoji["pencil"]
        )
        appearance_button.callback = self.appearance_callback

        settings_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="Settings", emoji=emoji["pencil"]
        )
        settings_button.callback = self.settings_callback

        items: List[discord.ui.Item] = []
        for t in shown:
            edit_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary, emoji=emoji["pencil"]
            )
            edit_button.callback = self._type_callback(t.ticket_base_name)

            prefix = f"{t.emoji} " if t.emoji else ""
            items.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=(
                            f"{prefix}**{t.label}**\n"
                            f"-# `{t.ticket_base_name}` | {len(t.ping_roles)} ping role(s) | {len(t.fields)} field(s)"
                        )
                    ),
                    accessory=edit_button,
                )
            )

        prev_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji=emoji["left"], disabled=self.page <= 1
        )
        prev_button.callback = self.previous_callback

        page_indicator: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=f"Page {self.page}/{self.max_page}",
            disabled=True,
        )

        next_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji=emoji["right"], disabled=self.page >= self.max_page
        )
        next_button.callback = self.next_callback

        self.add_item(
            discord.ui.Container(
                discord.ui.Section(
                    discord.ui.TextDisplay(content=f"### #{tv.id} {title}\n-# Posted in <#{tv.channel_id}>"),
                    accessory=back_button,
                ),
                discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                discord.ui.TextDisplay(
                    content=(
                        f"> **Panel message:** [Jump]({jump})\n"
                        f"> **Logging channel:** {logging_text}\n"
                        f"> **Ticket mode:** `{tv.ticket_type or 'not set'}`\n"
                        f"> **Staff roles:** {staff}"
                    )
                ),
                discord.ui.ActionRow(appearance_button, settings_button),
                discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                discord.ui.TextDisplay(content=f"### Ticket Sections"),
                *items,
                discord.ui.ActionRow(prev_button, page_indicator, next_button),
            )
        )

        add_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Add Section",
            emoji=emoji["plus"],
            disabled=len(tv.types) >= 25,
        )
        add_button.callback = self.add_type_callback

        remove_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Remove Section",
            emoji=emoji["trash"],
            disabled=len(tv.types) <= 1,  
        )
        remove_button.callback = self.remove_type_callback

        self.add_item(discord.ui.ActionRow(add_button, remove_button))

    async def refresh(
        self, interaction: discord.Interaction, tv: TicketView | None = None, page: int | None = None
    ) -> None:
        view = TicketPanelEdit(self.list_view, tv or self.tv, self.page if page is None else page)
        await edit_view(interaction, view)

    async def back_callback(self, interaction: discord.Interaction) -> None:
        await self.list_view.refresh(interaction, self.list_view.page)

    async def previous_callback(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction, page=self.page - 1)

    async def next_callback(self, interaction: discord.Interaction) -> None:
        await self.refresh(interaction, page=self.page + 1)

    async def appearance_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PanelAppearanceModal(self))

    async def settings_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PanelSettingsModal(self))

    async def add_type_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TicketTypeModal(self, self.tv))

    async def remove_type_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RemoveTypeModal(self))

    def _type_callback(self, base_name: str):
        async def callback(interaction: discord.Interaction) -> None:
            await edit_view(interaction, TicketTypeEdit(self, self.tv, base_name))

        return callback

class PanelAppearanceModal(discord.ui.Modal):
    def __init__(self, panel_view: TicketPanelEdit) -> None:
        super().__init__(title="Edit Panel Appearance")
        self.panel_view = panel_view
        panel = panel_view.tv.panel

        self.title_input = discord.ui.TextInput(
            label="Title", max_length=256, default=panel.title if panel else None
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=4000,
            default=panel.description if panel else None,
        )
        self.footer_input = discord.ui.TextInput(
            label="Footer Text", required=False, max_length=2048, default=panel.footer_text if panel else None
        )
        self.thumbnail_input = discord.ui.TextInput(
            label="Thumbnail URL", required=False, max_length=500, default=panel.thumbnail_url if panel else None
        )

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.footer_input)
        self.add_item(self.thumbnail_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        thumbnail = self.thumbnail_input.value.strip() or None
        if thumbnail and not thumbnail.startswith(("http://", "https://")):
            await interaction.response.send_message(
                embed=simple_embed("Thumbnail must be a valid http(s) URL.", "cross"), ephemeral=True
            )
            return

        await interaction.response.defer()

        def mutate(config: dict[str, Any]) -> None:
            config["PanelConfig"] = {
                "title": self.title_input.value,
                "description": self.description_input.value or None,
                "footer": {"text": self.footer_input.value or None},
                "thumbnail": {"url": thumbnail},
            }

        new_tv = await save_changes(interaction, self.panel_view.tv, mutate)
        if new_tv is not None:
            await self.panel_view.refresh(interaction, tv=new_tv)

class PanelSettingsModal(discord.ui.Modal):
    def __init__(self, panel_view: TicketPanelEdit) -> None:
        super().__init__(title="Edit Panel Settings")
        self.panel_view = panel_view
        tv = panel_view.tv

        self.log_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            placeholder="Channel for ticket logs",
            min_values=1,
            max_values=1,
            default_values=channel_defaults(tv.logging_channel_id),
        )
        self.mode_select = discord.ui.Select(
            placeholder="How tickets are created",
            options=[
                discord.SelectOption(label=name, value=key, default=key == tv.ticket_type)
                for key, name in TICKET_MODES.items()
            ],
        )
        self.staff_select = discord.ui.RoleSelect(
            placeholder="Roles that can manage tickets",
            min_values=0,
            max_values=25,
            required=False,
            default_values=role_defaults(tv.staff_role_ids),
        )

        self.add_item(discord.ui.Label(text="Logging Channel", component=self.log_select))
        self.add_item(discord.ui.Label(text="Ticket Mode", component=self.mode_select))
        self.add_item(discord.ui.Label(text="Higher Staff Roles", component=self.staff_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        def mutate(config: dict[str, Any]) -> None:
            basic = config["BasicConfigurations"]
            basic["TicketLoggingHandler"] = self.log_select.values[0].id
            basic["TicketType"] = self.mode_select.values[0]
            basic["higher_staffs_role_id"] = [r.id for r in self.staff_select.values]

        new_tv = await save_changes(interaction, self.panel_view.tv, mutate)
        if new_tv is not None:
            await self.panel_view.refresh(interaction, tv=new_tv)

class RemoveTypeModal(discord.ui.Modal):
    def __init__(self, panel_view: TicketPanelEdit) -> None:
        super().__init__(title="Remove Ticket Type")
        self.panel_view = panel_view

        self.select = discord.ui.Select(
            placeholder="Select a ticket type",
            options=[
                discord.SelectOption(label=t.label[:100], value=t.ticket_base_name)
                for t in panel_view.tv.types
            ],
        )
        self.add_item(discord.ui.Label(text="Ticket type to remove", component=self.select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        base_name = self.select.values[0]

        def mutate(config: dict[str, Any]) -> None:
            remaining = [t for t in config["Tickets"] if t["ticket_base_name"] != base_name]
            if not remaining:
                raise LilyError("A panel needs at least one ticket type.")
            config["Tickets"] = remaining

        new_tv = await save_changes(interaction, self.panel_view.tv, mutate)
        if new_tv is not None:
            await self.panel_view.refresh(interaction, tv=new_tv)

class TicketTypeEdit(discord.ui.LayoutView):
    def __init__(self, panel_view: TicketPanelEdit, tv: TicketView, base_name: str) -> None:
        super().__init__(timeout=None)

        self.panel_view = panel_view
        self.tv = tv
        self.base_name = base_name
        self.ticket = tv.get_type(base_name)

        back_button: discord.ui.Button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Back")
        back_button.callback = self.back_callback

        if self.ticket is None:
            self.add_item(
                discord.ui.Container(
                    discord.ui.Section(
                        discord.ui.TextDisplay(content="*This ticket type no longer exists.*"),
                        accessory=back_button,
                    )
                )
            )
            return

        t = self.ticket
        pings = " ".join(f"<@&{r}>" for r in t.ping_roles) or "*None*"
        category = f"<#{t.channel_id}>" if t.channel_id else "*Not set*"

        details_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="Details", emoji=emoji["pencil"]
        )
        details_button.callback = self.details_callback

        options_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="Options", emoji=emoji["pencil"]
        )
        options_button.callback = self.options_callback

        fields_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="Form Fields", emoji=emoji["pencil"]
        )
        fields_button.callback = self.fields_callback

        self.add_item(
            discord.ui.Container(
                discord.ui.Section(
                    discord.ui.TextDisplay(content=f"### {t.emoji + ' ' if t.emoji else ''}{t.label}"),
                    discord.ui.TextDisplay(content=f"- {t.description or '*None*'}"),
                    accessory=back_button,
                ),
                discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                discord.ui.TextDisplay(
                    content=(
                        f"**Base name:** `{t.ticket_base_name}`\n"
                        f"**Category / channel:** {category}\n"
                        f"**Channel emoji:** {t.channel_emoji or '*None*'}\n"
                        f"**Ping roles:** {pings}\n"
                    )
                ),
                discord.ui.ActionRow(details_button, options_button, fields_button)
            )
        )

    async def back_callback(self, interaction: discord.Interaction) -> None:
        await self.panel_view.refresh(interaction, tv=self.tv)

    async def details_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TicketTypeModal(self.panel_view, self.tv, self.ticket))

    async def options_callback(self, interaction: discord.Interaction) -> None:
        assert self.ticket is not None
        await interaction.response.send_modal(TicketTypeOptionsModal(self.panel_view, self.tv, self.ticket))

    async def fields_callback(self, interaction: discord.Interaction) -> None:
        await edit_view(interaction, TicketFieldsEdit(self.panel_view, self.tv, self.base_name))

class TicketTypeModal(discord.ui.Modal):
    def __init__(self, panel_view: TicketPanelEdit, tv: TicketView, ticket: TicketType | None = None) -> None:
        super().__init__(title="Edit Ticket Type" if ticket else "Add Ticket Type")

        self.panel_view = panel_view
        self.tv = tv
        self.ticket = ticket

        self.label_input = discord.ui.TextInput(
            label="Label", max_length=80, default=ticket.label if ticket else None
        )
        self.description_input = discord.ui.TextInput(
            label="Description", required=False, max_length=100, default=ticket.description if ticket else None
        )
        self.emoji_input = discord.ui.TextInput(
            label="Emoji", required=False, max_length=64, default=ticket.emoji if ticket else None
        )
        self.base_input = discord.ui.TextInput(
            label="Base Name (unique, used for channel names)",
            max_length=32,
            placeholder="e.g. support",
            default=ticket.ticket_base_name if ticket else None,
        )
        self.channel_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.category],
            placeholder="Category where tickets of this type are created",
            min_values=1,
            max_values=1,
            default_values=channel_defaults(ticket.channel_id if ticket else None),
        )

        self.add_item(self.label_input)
        self.add_item(self.description_input)
        self.add_item(self.emoji_input)
        if ticket is None:
            self.add_item(self.base_input)
        self.add_item(discord.ui.Label(text="Category / Channel", component=self.channel_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        label = self.label_input.value.strip()
        if self.ticket is None:
            base = self.base_input.value.strip().lower()
            if not BASE_NAME_RE.match(base):
                await interaction.response.send_message(
                    embed=simple_embed("Base name must be 1-32 chars: lowercase letters, numbers, `-` or `_`.", "cross"),
                    ephemeral=True,
                )
                return
            if base in {t.ticket_base_name for t in self.tv.types}:
                await interaction.response.send_message(
                    embed=simple_embed(f"Base name `{base}` is already used in this panel.", "cross"),
                    ephemeral=True,
                )
                return
        else:
            base = self.ticket.ticket_base_name

        taken = {t.ticket_base_name for t in self.tv.types}
        if self.ticket is not None:
            taken.discard(self.ticket.ticket_base_name)
        if base in taken:
            await interaction.response.send_message(
                embed=simple_embed(f"Base name `{base}` is already used in this panel.", "cross"),
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        values = {
            "label": label,
            "description": self.description_input.value.strip() or None,
            "emoji": self.emoji_input.value.strip() or None,
            "channel_id": self.channel_select.values[0].id if self.channel_select.values else None,
            "ticket_base_name": base,
        }

        def mutate(config: dict[str, Any]) -> None:
            if self.ticket is None:
                if len(config["Tickets"]) >= 25:
                    raise LilyError(f"A panel can hold at most {25} ticket types.")
                config["Tickets"].append({**values, "channel_emoji": None, "fields": [dict(f) for f in DEFAULT_FIELDS], "ping_roles": []})
            else:
                find_ticket(config, self.ticket.ticket_base_name).update(values)

        new_tv = await save_changes(interaction, self.tv, mutate)
        if new_tv is not None:
            await edit_view(interaction, TicketTypeEdit(self.panel_view, new_tv, base))

class TicketTypeOptionsModal(discord.ui.Modal):
    def __init__(self, panel_view: TicketPanelEdit, tv: TicketView, ticket: TicketType) -> None:
        super().__init__(title="Ticket Type Options")

        self.panel_view = panel_view
        self.tv = tv
        self.ticket = ticket

        self.emoji_input = discord.ui.TextInput(
            label="Channel Emoji", required=False, max_length=64, default=ticket.channel_emoji
        )
        self.ping_select = discord.ui.RoleSelect(
            placeholder="Roles pinged when a ticket opens",
            min_values=0,
            max_values=25,
            required=False,
            default_values=role_defaults(ticket.ping_roles),
        )

        self.add_item(self.emoji_input)
        self.add_item(discord.ui.Label(text="Ping Roles", component=self.ping_select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        base = self.ticket.ticket_base_name

        def mutate(config: dict[str, Any]) -> None:
            entry = find_ticket(config, base)
            entry["channel_emoji"] = self.emoji_input.value.strip() or None
            entry["ping_roles"] = [r.id for r in self.ping_select.values]

        new_tv = await save_changes(interaction, self.tv, mutate)
        if new_tv is not None:
            await edit_view(interaction, TicketTypeEdit(self.panel_view, new_tv, base))

class FieldTypePicker(discord.ui.LayoutView):
    def __init__(self, fields_view: TicketFieldsEdit, index: int | None = None) -> None:
        super().__init__(timeout=None)

        assert fields_view.ticket is not None
        self.fields_view = fields_view
        self.index = index

        fields = fields_view.ticket.fields
        current = fields[index] if index is not None and index < len(fields) else None
        self.current_type = current.get("type", "short") if current else None

        self.type_select = discord.ui.Select(
            placeholder="Choose a field type...",
            options=[
                discord.SelectOption(
                    label=name, description=description, value=key, default=key == self.current_type
                )
                for key, (name, description) in FIELD_TYPES.items()
            ],
        )
        self.type_select.callback = self.type_callback

        back_button: discord.ui.Button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Back")
        back_button.callback = self.back_callback

        rows: List[discord.ui.Item] = [discord.ui.ActionRow(self.type_select)]
        if self.current_type in FIELD_TYPES:
            keep_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=f"Keep {FIELD_TYPES[self.current_type][0]}",
            )
            keep_button.callback = self.keep_callback
            rows.append(discord.ui.ActionRow(keep_button))

        action = "Edit" if index is not None else "Add"
        self.add_item(
            discord.ui.Container(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=f"### {action} Form Field\n-# Step 1/2: choose the field type"
                    ),
                    accessory=back_button,
                ),
                discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                *rows,
            )
        )

    async def type_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            TicketFieldModal(self.fields_view, self.index, self.type_select.values[0])
        )

    async def keep_callback(self, interaction: discord.Interaction) -> None:
        assert self.current_type is not None
        await interaction.response.send_modal(
            TicketFieldModal(self.fields_view, self.index, self.current_type)
        )

    async def back_callback(self, interaction: discord.Interaction) -> None:
        await self.fields_view.refresh(interaction, self.fields_view.tv)

class TicketFieldsEdit(discord.ui.LayoutView):
    def __init__(self, panel_view: TicketPanelEdit, tv: TicketView, base_name: str) -> None:
        super().__init__(timeout=None)

        self.panel_view = panel_view
        self.tv = tv
        self.base_name = base_name
        self.ticket = tv.get_type(base_name)

        back_button: discord.ui.Button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Back")
        back_button.callback = self.back_callback

        if self.ticket is None:
            self.add_item(
                discord.ui.Container(
                    discord.ui.Section(
                        discord.ui.TextDisplay(content="*This ticket type no longer exists.*"),
                        accessory=back_button,
                    )
                )
            )
            return

        fields = list(self.ticket.fields)
        types = [f.get("type", "short") for f in fields]

        items: List[discord.ui.Item] = []
        for index, field in enumerate(fields):
            edit_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.secondary, emoji=emoji["pencil"]
            )
            edit_button.callback = self._edit_callback(index)

            ftype = field.get("type", "short")
            label, description = FIELD_TYPES.get(ftype, (ftype, ""))

            details = [label, description] if description else [label]

            if ftype in TEXT_FIELD_TYPES:
                details.append(f"max {field.get('length', 100)} chars")

            if field.get("metadata"):
                details.append(f"options: {field['metadata'][:60]}")

            if ftype in ("selector", "check_box") and field.get("min_values") is not None:
                details.append(f"pick {field['min_values']}-{field['max_values']}")

            items.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=f"**{index + 1}. {field.get('label') or '?'}**\n-# {' | '.join(details)}"
                    ),
                    accessory=edit_button,
                )
            )

        notes: list[str] = []
        if not fields:
            notes.append("Add at least one field, otherwise the ticket form can't open.")
        if notes:
            items.append(discord.ui.TextDisplay(content="\n".join(f"-# Note: {n}" for n in notes)))

        self.add_item(
            discord.ui.Container(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=f"## Form Fields | {self.ticket.label}\n-# {len(fields)}/{5} fields",
                    ),
                    accessory=back_button,
                ),
                discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                *items,
            )
        )

        add_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Add Field",
            emoji=emoji["plus"],
            disabled=len(fields) >= 5,
        )
        add_button.callback = self.add_callback

        remove_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Remove Field",
            emoji=emoji["trash"],
            disabled=not fields,
        )
        remove_button.callback = self.remove_callback

        self.add_item(discord.ui.ActionRow(add_button, remove_button))

    async def refresh(self, interaction: discord.Interaction, tv: TicketView) -> None:
        await edit_view(interaction, TicketFieldsEdit(self.panel_view, tv, self.base_name))

    async def back_callback(self, interaction: discord.Interaction) -> None:
        await edit_view(interaction, TicketTypeEdit(self.panel_view, self.tv, self.base_name))

    async def add_callback(self, interaction: discord.Interaction) -> None:
        await edit_view(interaction, FieldTypePicker(self))

    def _edit_callback(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
            await edit_view(interaction, FieldTypePicker(self, index))

        return callback

    async def remove_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RemoveFieldModal(self))

class TicketFieldModal(discord.ui.Modal):
    def __init__(self, fields_view: TicketFieldsEdit, index: int | None = None, ftype: str = "short") -> None:
        type_name = FIELD_TYPES.get(ftype, (ftype, ""))[0]
        super().__init__(title=f"{'Edit' if index is not None else 'Add'} {type_name} Field"[:45])

        assert fields_view.ticket is not None
        self.fields_view = fields_view
        self.index = index
        self.ftype = ftype

        existing = fields_view.ticket.fields
        current = existing[index] if index is not None and index < len(existing) else {}
        if current.get("type") != ftype:
            current = {"label": current.get("label"), "description": current.get("description")}

        self.label_input = discord.ui.TextInput(
            label="Label (shown above the input)",
            max_length=45,
            default=current.get("label"),
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            required=False,
            max_length=100,
            default=current.get("description") or None,
        )
        self.add_item(self.label_input)
        self.add_item(self.description_input)

        self.length_input: discord.ui.TextInput | None = None
        self.options_input: discord.ui.TextInput | None = None
        self.min_input: discord.ui.TextInput | None = None
        self.max_input: discord.ui.TextInput | None = None

        if ftype in TEXT_FIELD_TYPES:
            self.length_input = discord.ui.TextInput(
                label="Max Length",
                required=False,
                max_length=4,
                placeholder="100",
                default=str(current["length"]) if current.get("length") is not None else None,
            )
            self.add_item(self.length_input)

        if ftype in OPTION_FIELD_TYPES:
            self.options_input = discord.ui.TextInput(
                label="Options (comma separated)",
                style=discord.TextStyle.paragraph,
                max_length=1500,
                placeholder="e.g. Bug report, Billing, Other",
                default=current.get("metadata") or None,
            )
            self.add_item(self.options_input)

        if ftype in ("selector", "check_box"):
            self.min_input = discord.ui.TextInput(
                label="Min Selections",
                required=False,
                max_length=2,
                placeholder="1",
                default=str(current["min_values"]) if current.get("min_values") is not None else None,
            )
            self.max_input = discord.ui.TextInput(
                label="Max Selections",
                required=False,
                max_length=2,
                placeholder="1",
                default=str(current["max_values"]) if current.get("max_values") is not None else None,
            )
            self.add_item(self.min_input)
            self.add_item(self.max_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert self.fields_view.ticket is not None

        async def reject(text: str) -> None:
            await interaction.response.send_message(embed=simple_embed(text, "cross"), ephemeral=True)

        label = self.label_input.value.strip()
        description = self.description_input.value.strip()
        if not label:
            await reject("A field needs a label.")
            return

        others = [f for i, f in enumerate(self.fields_view.ticket.fields) if i != self.index]
        if self.ftype == "file_upload" and any(f.get("type") == "file_upload" for f in others):
            await reject("A form can only have one file upload field.")
            return

        entry: dict[str, Any] = {"label": label, "type": self.ftype}
        if description:
            entry["description"] = description

        if self.length_input is not None:
            length_text = self.length_input.value.strip()
            length = 100
            if length_text:
                if not length_text.isdigit() or not 1 <= int(length_text) <= 4000:
                    await reject("Max length must be a number between 1 and 4000.")
                    return
                length = int(length_text)
            entry["length"] = length

        options: list[str] = []
        if self.options_input is not None:
            options = list(dict.fromkeys(o.strip() for o in self.options_input.value.split(",") if o.strip()))
            limit = MAX_SELECT_OPTIONS if self.ftype == "selector" else MAX_RADIO_OPTIONS
            minimum = 1 if self.ftype == "check_box" else 2
            if not minimum <= len(options) <= limit:
                await reject(f"Provide {minimum}-{limit} unique options, separated by commas.")
                return
            if any(len(o) > 100 for o in options):
                await reject("Each option can be at most 100 characters.")
                return
            entry["metadata"] = ", ".join(options)

        if self.ftype == "selector" or (self.ftype == "check_box" and len(options) > 1):
            assert self.min_input is not None and self.max_input is not None
            try:
                min_values = int(self.min_input.value.strip() or 1)
                max_default = len(options) if self.ftype == "check_box" else 1
                max_values = int(self.max_input.value.strip() or max_default)
            except ValueError:
                await reject("Min and max selections must be numbers.")
                return
            if not 1 <= min_values <= max_values <= len(options):
                await reject(f"Selections must satisfy 1 <= min <= max <= {len(options)} (the number of options).")
                return
            entry["min_values"] = min_values
            entry["max_values"] = max_values

        await interaction.response.defer()

        base = self.fields_view.base_name

        def mutate(config: dict[str, Any]) -> None:
            fields = find_ticket(config, base)["fields"]
            if self.index is None:
                if len(fields) >= 5:
                    raise LilyError("A form can hold at most 5 fields.")
                fields.append(entry)
            else:
                if self.index >= len(fields):
                    raise LilyError("That field no longer exists.")
                old = fields[self.index]
                for key in ("description", "length", "metadata", "min_values", "max_values"):
                    old.pop(key, None)
                old.update(entry)

        new_tv = await save_changes(interaction, self.fields_view.tv, mutate)
        if new_tv is not None:
            await self.fields_view.refresh(interaction, new_tv)

class RemoveFieldModal(discord.ui.Modal):
    def __init__(self, fields_view: TicketFieldsEdit) -> None:
        super().__init__(title="Remove Form Field")
        assert fields_view.ticket is not None
        self.fields_view = fields_view

        self.select = discord.ui.Select(
            placeholder="Select a field",
            options=[
                discord.SelectOption(label=f"{i + 1}. {f.get('label') or '?'}"[:100], value=str(i))
                for i, f in enumerate(fields_view.ticket.fields)
            ],
        )
        self.add_item(discord.ui.Label(text="Field to remove", component=self.select))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        index = int(self.select.values[0])
        base = self.fields_view.base_name

        def mutate(config: dict[str, Any]) -> None:
            fields = find_ticket(config, base)["fields"]
            if index >= len(fields):
                raise LilyError("That field no longer exists.")
            fields.pop(index)

        new_tv = await save_changes(interaction, self.fields_view.tv, mutate)
        if new_tv is not None:
            await self.fields_view.refresh(interaction, new_tv)