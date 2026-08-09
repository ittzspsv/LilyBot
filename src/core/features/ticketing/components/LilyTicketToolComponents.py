from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, cast
import re

import discord
from discord.ext import commands
from discord.ext.commands import MemberConverter

from src.core.configs.sBotDetails import (
    emoji,
    img,
)

from src.core.features.moderation.components.sLilyModerationComponents import (
    action_log,
    CaseListView
)


from src.core.utils.embeds.sLilyEmbed import (
    simple_embed,
)

from src.core.features.moderation.controller.lily_moderation_controller import (
    mute_user,
    quarantine_user,
    warn
)

from ..classes.ticketing_classes import (
    DatabaseAccess,
)

bot = None

""" Modals for ticket panel moderation. This is indeed redundant, but we only have access to logging database, so we need to evaluate it again!"""
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


    def __init__(self, db: DatabaseAccess, member_id: int, proofs: List[str]) -> None:
        super().__init__(title="Mute User")

        self.db = db

        self.member_id = member_id
        self.proofs = proofs

    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(self.duration.component, discord.ui.TextInput)
        assert isinstance(self.reason.component, discord.ui.TextInput)

        if interaction.guild is None:
            await interaction.response.send_message(embed=simple_embed("Command requires guild object inorder to execute", 'cross'), ephemeral=True)
            return
        
        user: Optional[discord.Member] = None
        try:
            user = await interaction.guild.fetch_member(self.member_id)
        except discord.NotFound:
            await interaction.response.send_message(embed=simple_embed("User is not in the guild!", 'cross'), ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.response.send_message(embed=simple_embed("Failed to fetch the member due to network error!", 'cross'), ephemeral=True)
            return
        except Exception:
            await interaction.response.send_message(embed=simple_embed("Failed to fetch the member due to unknown error!", 'cross'), ephemeral=True)
            return
        
        await interaction.response.defer()
        
        await mute_user(
            interaction,
            user,
            self.duration.component.value,
            self.reason.component.value,
            self.proofs
        )

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


    def __init__(self, db: DatabaseAccess, member_id: int, proofs: List[str]) -> None:
        super().__init__(title="Ban User")

        self.db = db

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
            await interaction.response.send_message(embed=simple_embed("User should be in the guild in-order to quarantine him", 'cross'), ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.response.send_message(embed=simple_embed("Failed to fetch the member due to network error!", 'cross'), ephemeral=True)
            return
        except Exception:
            await interaction.response.send_message(embed=simple_embed("Failed to fetch the member due to unknown error!", 'cross'), ephemeral=True)
            return
        
        await interaction.response.defer()

        await quarantine_user(
            interaction,
            member,
            self.reason.component.value,
            self.proofs
        )

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


    def __init__(self, db: DatabaseAccess, member_id: int, proofs: List[str]) -> None:
        super().__init__(title="Warn User")

        self.db = db

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
            await interaction.response.send_message(embed=simple_embed("User should be in the guild in-order to quarantine him", 'cross'), ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.response.send_message(embed=simple_embed("Failed to fetch the member due to network error!", 'cross'), ephemeral=True)
            return
        except Exception:
            await interaction.response.send_message(embed=simple_embed("Failed to fetch the member due to unknown error!", 'cross'), ephemeral=True)
            return
        
        await warn(
            interaction,
            member,
            self.reason.component.value,
            self.proofs
        )

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

class TicketComponentEmbed(discord.ui.LayoutView):
    def __init__(self, opener: discord.Member | int, ticket_channel_id: int, submission_json: dict, core_json: dict, db: DatabaseAccess):
        super().__init__(timeout=None)

        self.opener: Optional[discord.Member] = opener if isinstance(opener, discord.Member) else None
        self.db = db
        if isinstance(opener, discord.Member):
            self.opener_id = opener.id
        elif isinstance(opener, int):
            self.opener_id = opener
        else:
            raise ValueError("Invalid Opener Type")
        
        self.ticket_channel_id: int = ticket_channel_id
        self.misc: Dict = {}

        self.submission_json = submission_json
        self.core_json = core_json

        base_name = self.submission_json.get("ticket_name_base", "ticket")
        self.ticket_name: str = base_name.replace("_", " ").title()
        roles = submission_json.get("ping_roles", [])
        self.ticket_mentions: str = " ".join(f"<@&{role_id}>" for role_id in roles) if roles else "No Mentions!"


        self.allowed_roles = set(submission_json.get("ping_roles", []))
        self.higher_staff_role_ids = set(self.core_json.get("BasicConfigurations").get("higher_staffs_role_id"))


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

        
        self.case_list_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["logs"],
            custom_id=f"case-list{self.ticket_channel_id}",
        )

        self.case_list_button.callback = self.case_list_callback

        self.ban_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["ban_hammer"],
            custom_id=f"ban{self.ticket_channel_id}",
        )

        self.ban_button.callback = self.ban_callback

        self.mute_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["member"],
            custom_id=f"mute{self.ticket_channel_id}",
        )

        self.mute_button.callback = self.mute_callback

        self.warn_button: discord.ui.Button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=emoji["warn"],
            custom_id=f"warn{self.ticket_channel_id}",
        )

        self.warn_button.callback = self.warn_callback

        self.claim_ticket.callback = self.claim_ticket_callback
        self.revoke_claim.callback = self.revoke_claim_callback

        opener_details = submission_json.get("opener", {})

        avatar_url = (
            self.opener.display_avatar.url
            if isinstance(self.opener, discord.Member)
            else opener_details.get("avatar")
        )


        content = (
            f"- **ID**: {opener_details.get("member_id", 0)}\n"
            f"- **Created on**: {opener_details.get("created_on")}\n"
            f"- **Joined on**: {opener_details.get("joined_on")}"
            if opener_details is not None
            else "**User information unavailable**"
        ) 

        mention = (
            self.opener.mention
            if isinstance(self.opener, discord.Member)
            else f"<@{opener_details.get("member_id")}>"
        )


        base_container = discord.ui.Container(
            discord.ui.TextDisplay(content=f"# {self.ticket_name}"),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.Section(
                discord.ui.TextDisplay(content=f"### Ticket Opener Information | {mention}"),
                discord.ui.TextDisplay(content=content),
                accessory=discord.ui.Thumbnail(
                    media=avatar_url,
                ),
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content=f"-# {self.ticket_mentions}"),
        )

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


        ticket_details_container = discord.ui.Container(
            discord.ui.TextDisplay(
                "## Ticket Details"
            ),
            *ticket_details
        )

        self.add_item(base_container)
        self.add_item(ticket_details_container)
        self.add_item(discord.ui.ActionRow(self.claim_ticket, self.revoke_claim))

    async def _check_permissions(self, interaction: discord.Interaction) -> bool:
        assert isinstance(interaction.user, discord.Member)
        is_staff = any(role.id in self.allowed_roles for role in interaction.user.roles)
        is_opener = interaction.user.id == self.opener_id

        if not is_staff or is_opener:
            await interaction.response.send_message(
                embed=simple_embed("You are not allowed to use this!", 'cross'),
                ephemeral=True
            )
            return False

        if interaction.guild is None:
            return False

        return True

    async def claim_ticket_callback(self, interaction: discord.Interaction) -> None:
        if interaction.channel is None or interaction.guild is None:
            return

        await interaction.response.defer()
        assert isinstance(interaction.user, discord.Member)

        is_staff = any(role.id in self.allowed_roles for role in interaction.user.roles)
        is_opener = interaction.user.id == self.opener_id

        if not is_staff or is_opener:
            await interaction.followup.send(
                embed=simple_embed("You are not allowed to claim this ticket!", 'cross'),
                ephemeral=True
            )
            return

        success = await self.db.bot_db.set_ticket_claimer(interaction.user.id, interaction.channel.id, interaction.guild.id)
        if not success:
            claimer = await self.db.bot_db.get_ticket_claimer(interaction.channel.id)
            await interaction.followup.send(
                embed=simple_embed(f"<@{claimer}> has already claimed this ticket!", 'cross'),
                ephemeral=True
            )
            return

        channel = interaction.channel
        if isinstance(channel, discord.TextChannel) and isinstance(interaction.user, discord.Member):
            await channel.set_permissions(
                interaction.user,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                add_reactions=True,
                use_external_emojis=True,
                read_message_history=True
            )

        self.claim_ticket.disabled = True
        self.claim_ticket.label = "Claimed"
        self.claim_ticket.style = discord.ButtonStyle.secondary
        self.ticket_message = interaction.message
        assert interaction.message is not None
        await interaction.message.edit(view=self)
        await interaction.followup.send(embed=simple_embed(f"{interaction.user.mention} has claimed the ticket!"))

    async def revoke_claim_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        if interaction.channel is None or interaction.guild is None:
            return
        
        claimer = await self.db.bot_db.get_ticket_claimer(interaction.channel.id)


        if claimer is None:
            await interaction.followup.send(
                embed=simple_embed("No one has claimed this ticket!", 'cross'),
                ephemeral=True
            )
            return
        

        claimer_member: Optional[discord.Member] = None

        if claimer is not None:
            try:
                claimer_member = await interaction.guild.fetch_member(claimer)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                claimer_member = None

        assert isinstance(interaction.user, discord.Member)
        if (interaction.user.id != claimer and not any(role.id in self.higher_staff_role_ids for role in interaction.user.roles)):            
            await interaction.followup.send(
                embed=simple_embed("You are not allowed to revoke ticket claims!", 'cross'),
                ephemeral=True
            )
            return

        if claimer is None:
            await interaction.followup.send(
                embed=simple_embed("This ticket is not currently claimed.", 'cross'),
                ephemeral=True
            )
            return

        channel = interaction.channel
        if claimer_member is not None and isinstance(channel, discord.TextChannel):
            await channel.set_permissions(claimer_member, overwrite=None)  


        self.claim_ticket.disabled = False
        self.claim_ticket.label = "Claim"
        self.claim_ticket.style = discord.ButtonStyle.secondary

        await self.db.bot_db.reset_ticket_claimer(interaction.channel.id)

        if interaction.message:
            await interaction.message.edit(view=self)

        await interaction.followup.send(
            embed=simple_embed("Ticket claim has been revoked!"),
            ephemeral=True
        )

        assert isinstance(channel, discord.TextChannel)

        await channel.send(
            embed=simple_embed(f"{interaction.user.mention} revoked the ticket claim.")
        )

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

        _guild_id = self.db.bot_db.get_secondary_guild_id(interaction.guild.id) or interaction.guild.id
        
        """ Fetch modlogs of the given member """
        payload = {
            "guild_id": _guild_id,
            "target_user_id": member_data["id"],
            "moderator_id": None,
            "mod_type": "all"
        }

        result = await self.db.bot_db.fetch_mod_logs(**payload)
        if not result["success"]:
            await interaction.response.send_message(embed=simple_embed("No cases found.", 'cross'), ephemeral=True)
            return  

        view = CaseListView((member_data["username"], member_data["avatar"]), result, self.db.bot_db)

        await interaction.response.send_message(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True
        )

    async def ban_callback(self, interaction: discord.Interaction):
        if not await self._check_permissions(interaction):
            return

        await interaction.response.send_modal(
            BanModal(
                db=self.db,
                member_id=self.misc["reported_member"]["id"],
                proofs=self.misc["proofs"]
            )
        )

    async def mute_callback(self, interaction: discord.Interaction):
        if not await self._check_permissions(interaction):
            return

        await interaction.response.send_modal(
            MuteModal(
                db=self.db,
                member_id=self.misc["reported_member"]["id"],
                proofs=self.misc["proofs"]
            )
        )

    async def warn_callback(self, interaction: discord.Interaction):
        if not await self._check_permissions(interaction):
            return

        await interaction.response.send_modal(
            WarnModal(
                db=self.db,
                member_id=self.misc["reported_member"]["id"],
                proofs=self.misc["proofs"]
            )
        )
        
class TicketModal(discord.ui.Modal):
    def __init__(self, title: str, modal_data: dict, json_data, db: DatabaseAccess, message: discord.Message):
        super().__init__(title=title)

        if not isinstance(modal_data, dict):
            raise TypeError(f"modal_data must be a dict, got {type(modal_data)}")

        self.db: DatabaseAccess = db
        self.components: List[Dict] = []
        self.modal_data = modal_data
        self.json_data = json_data
        self.converter = MemberConverter()
        self.message = message

        self.fields = self.modal_data.get("fields")

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
            if field_type in ("member", "long", "short"):
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
        

    async def ticket_thread_constructor(self, interaction: discord.Interaction, core_json, submission_json) -> discord.TextChannel | discord.Thread | None:
        if interaction.guild is None:
            return None

        channel_id: int = int(submission_json.get("channel_id"))
        
        proof_attachments = submission_json.get("proof_images")
        proofs_flag = False
        if proof_attachments:
            proof_url = '\n'.join(proof_attachments)
            proofs_flag = True
        else:
            proof_url = "No Proofs Attached!"
            proofs_flag = False

        roles = submission_json.get("ping_roles", [])

        higher_staff_roles_ids = core_json.get("BasicConfigurations").get("higher_staffs_role_id")

        opener = interaction.user
        logging_channel_id = core_json.get("BasicConfigurations").get("TicketLoggingHandler")
        ticket_name_base = submission_json.get("ticket_name_base")
        channel_emoji = submission_json.get("channel_emoji", "")
        ticket_name = f"{channel_emoji}{ticket_name_base}"
    
        channel_category = interaction.guild.get_channel(channel_id)

        if not isinstance(channel_category, discord.CategoryChannel):
            channel_category = await interaction.guild.fetch_channel(channel_id)

        if not isinstance(channel_category, discord.CategoryChannel):
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
            read_message_history=True
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
                    create_private_threads=False
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
                    create_private_threads=False
                )
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

        if not isinstance(opener, discord.Member):
            return

        view = TicketComponentEmbed(opener=opener, ticket_channel_id=text_channel.id, submission_json=submission_json, core_json=core_json, db=self.db)
        ticket_message: discord.Message = await text_channel.send(view=view)

        """ Pin the message to the channel so that it's easily viewable """
        try:
            await ticket_message.pin()
        except discord.Forbidden:
            pass

        if proofs_flag:
            await text_channel.send(content=f"{proof_url}")

        await self.db.bot_db.create_ticket(
            text_channel.id,
            interaction.guild.id,
            opener.id,
            ticket_name_base,
            logging_channel_id,
            submission_json,
            ticket_message.id
        )
        return text_channel

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return

        await interaction.response.defer(ephemeral=True)

        rows = await self.db.bot_db.get_ticket_by_opener(interaction.user.id, interaction.guild.id)

        if len(rows) >= 3:
            references = ", ".join(f"<#{r[0]}>" for r in rows)
            await interaction.followup.send(
                embed=simple_embed(
                    "Your ticket cannot be created.\n"
                    "Please close your previous tickets first.\n"
                    f"**References:** {references}"
                ),
                ephemeral=True
            )
            return

        channel_id = self.modal_data.get("channel_id")
        ticket_name_base = self.modal_data.get("ticket_base_name", "ticket")
        channel_emoji = self.modal_data.get("channel_emoji", "")
        ping_roles = self.modal_data.get("ping_roles", [])
        logs_channel_id  = self.json_data["BasicConfigurations"]["TicketLoggingHandler"]

        field_data: List[Dict] = []

        bot: commands.Bot = cast(commands.Bot, interaction.client)
        ctx = await bot.get_context(self.message)

        for data in self.components:
            field = data["field"]
            item = data["item"]

            field_type = field["type"]

            if field_type == "file_upload":
                field_data.append({
                    "field": field,
                    "value": [attachment.url for attachment in item.component.values]
                })
            elif field_type == "member":
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
                except:
                    field_data.append({
                        "field": field,
                        "value": {
                            "flag": 1,
                            "username": item.component.value
                        }
                    })

                ...
            
            elif field_type == "role_select":
                field_data.append({
                    "field": field,
                    "value": [role.name for role in item.component.values]
                })

            else:
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
            "higher_staff_role_ids": self.json_data.get("BasicConfigurations").get("higher_staffs_role_id"),
            "fields": self.fields,
            "field_data": field_data,
            "ticket_name_base": ticket_name_base,
            "channel_emoji": channel_emoji,
            "logs_channel_id" : logs_channel_id,
            "ping_roles" : ping_roles
        }
        thread_channel: discord.TextChannel | discord.Thread | None = await self.ticket_thread_constructor(
            interaction,
            self.json_data,
            submission
        )

        if thread_channel is not None:
            await interaction.followup.send(
                embed=simple_embed(
                    f"Your ticket has been created: {thread_channel.mention}"
                ),
                ephemeral=True
            )

class TicketSelectComponent(discord.ui.LayoutView):
    def __init__(self, json_data: dict, db: DatabaseAccess) -> None:
        super().__init__(timeout=None)

        self.json_data = json_data
        self.db = db
        self.tickets = json_data.get("Tickets", [])
        panel_config = json_data.get("PanelConfig", {})

        self.ticket_options = discord.ui.Select(
                            placeholder="Choose a ticket type...",
                            custom_id="ticket_selector_main",
                            options=[
                                discord.SelectOption(
                                    label=ticket["label"],
                                    emoji=ticket.get("emoji", None),
                                    description=ticket.get("description", None),
                                    value=str(index)
                                )
                                for index, ticket in enumerate(self.tickets)
                            ]
                        )

        self.ticket_options.callback = self.ticket_selector_callback

        container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content=f"## {panel_config["title"]}"),
                discord.ui.TextDisplay(content=panel_config["description"]),
                accessory=discord.ui.Thumbnail(
                    media=panel_config["thumbnail"]["url"],
                ),
            ),
            discord.ui.ActionRow(
                self.ticket_options
            )       
        )

        self.add_item(container)

    async def ticket_selector_callback(self, interaction: discord.Interaction):
        selected_index = int(self.ticket_options.values[0])
        selected_ticket = self.tickets[selected_index]

        assert interaction.message is not None
        modal = TicketModal(
            title=selected_ticket["label"],
            modal_data=selected_ticket,
            json_data=self.json_data,
            db=self.db,
            message=interaction.message
        )

        await interaction.response.send_modal(modal)

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