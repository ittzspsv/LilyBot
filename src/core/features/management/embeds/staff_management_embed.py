import discord

from src.core.configs.bot_details import emoji, img
from discord.ext import commands
from typing import Optional
from datetime import datetime
from zoneinfo import ZoneInfo

def build_staff_embed(staff: discord.Member | discord.User, data: dict) -> discord.Embed:
    name = data.get("name")
    role_name = data.get("role_name")
    is_loa = data.get("is_loa")
    strikes_count = data.get("strikes_count")
    joined_on = data.get("joined_on")
    timezone = data.get("timezone")
    responsibility = data.get("responsibility")
    retired = data.get("retired")

    if is_loa == 1:
        status_display = f"{emoji['dnd']} On Leave"
    elif retired == 1:
        status_display = f"{emoji['invisible']} Retired"
    else:
        status_display = f"{emoji['online']} Active"

    if timezone is not None:
        local_dt = datetime.now(tz=ZoneInfo(timezone))
        current_time = local_dt.strftime("%-d %A %Y at %-I.%M%p").replace("AM", "am").replace("PM", "pm")
    else:
        current_time = "N/A"

    embed = discord.Embed(
        color=0xFFFFFF,
        title=f"{name}'s Profile",
    )

    embed.set_thumbnail(
        url=staff.avatar.url if staff.avatar else staff.default_avatar.url
    )

    embed.set_image(
        url="https://media.discordapp.net/attachments/1404797630558765141/1437432525739003904/colorbarWhite.png?format=webp&quality=lossless"
    )

    embed.add_field(
        name="__Basic Information__",
        value=(
            f"{emoji['shield']} **Role:** {','.join(role_name or []) or 'N/A'}\n"
            f"{emoji['bookmark']} **Responsibilities:** {responsibility or 'N/A'}\n"
            f"{emoji['calender']} **Join Date:** <t:{joined_on}:D>"
        ),
        inline=False,
    )

    embed.add_field(
        name="__Timezone Information__",
        value=(
            f"{emoji['clock']} **Timezone:** {timezone or 'N/A'}\n"
            f"{emoji['clock']} **Current Time:** {current_time}\n"
        )
    )

    embed.add_field(
        name="__Experience Information__",
        value=f"{emoji['clock']} **Evaluated Experience:** <t:{joined_on}:R>",
        inline=False,
    )

    embed.add_field(
        name="__Strikes Information__",
        value=f"{emoji['logs']} **Strike Count:** **{strikes_count}**",
        inline=False,
    )

    embed.add_field(
        name="__Status__",
        value=f"{status_display}\n",
        inline=False,
    )

    return embed

def build_staff_update_embed(
    staff: discord.Member | discord.User,
    handled_staff: discord.Member | discord.User,
    reason: str,
    img: dict
) -> discord.Embed:

    if staff and isinstance(staff, discord.Member):
        embed = discord.Embed(
            color=0xFFFFFF,
            title="Staff Update Information",
            description=f"### {staff.mention} has been removed from the team",
        )

        
        embed.set_thumbnail(url=staff.display_avatar.url)

        embed.set_image(url=img["border"])

        embed.add_field(
            name="Handled by",
            value=handled_staff.mention,
            inline=False,
        )

        embed.add_field(
            name="Reason",
            value=f"- {reason}",
            inline=False,
        )

        return embed
    else:
        return discord.Embed()
    
def build_no_strikes_embed(staff: discord.Member) -> discord.Embed:
    return (
        discord.Embed(
            color=0xf50000,
            title=f"{emoji['cross']} No Strikes Found",
            description=f"No strikes found for {staff.mention}.",
        )
        .set_thumbnail(url=staff.display_avatar.url or img["member"])
        .set_footer(text="Immutable Records • Managed by Lily System")
    )

def build_strikes_list_embed(
        staff: discord.Member, 
        strikes: list[dict]
    ) -> discord.Embed:
    embed = discord.Embed(
        color=0xFFFFFF,
        title=f"{emoji['arrow']} {staff.display_name}'s Infractions",
        description=f"{emoji['bookmark']} Listing all infractions issued to {staff.mention}",
    )

    embed.set_thumbnail(url=staff.display_avatar.url)
    embed.set_image(url=img["border"])

    for strike in strikes:
        issued_date = strike["date"]
        dt = datetime.fromisoformat(issued_date)
        issued_unix = int(dt.timestamp())

        expiry_date = strike["expiry_date"]
        expired_unix = 0
        if expiry_date:
            dt = datetime.fromisoformat(expiry_date)
            expired_unix = int(dt.timestamp())

        strike_type = strike.get("type") or "Strike"
        embed.add_field(
            name=f"{emoji['pencil']} __Infraction ID: {strike['strike_id']}__ | {strike_type.title()}",
            value=(
                f"> {emoji['bookmark']} **Reason** : {strike['reason']}\n"
                #f"> {emoji['shield']} **Manager** : <@{strike['manager']}>\n"
                f"> {emoji['calender']} **Date** : <t:{issued_unix}:R>\n"
                #f"> {emoji['clock']} **Expires**: "
                #f"{f'<t:{expired_unix}:R>' if expiry_date else 'Never'}\n"
            ),
            inline=False,
        )

    embed.set_footer(text="Immutable Records • Can only be removed by higher staff")

    return embed

def build_staff_update_result_embed(
    staff: discord.Member,
    interaction: discord.Interaction,
    old_role_id: int | None,
    new_role_id: int | None,
    reason: str,
    update_type: str
) -> discord.Embed:

    act = "promoted" if update_type == "promotion" else "demoted"

    embed = discord.Embed(
        color=0xFFFFFF,
        title=f"{update_type.title()} Information",
        description=(
            f"### {staff.mention} has been {act}!\n"
            f"### <@&{old_role_id}> -> <@&{new_role_id}>"
        )
    )

    embed.set_thumbnail(url=staff.display_avatar.url)
    embed.set_image(url=img["border"])

    embed.add_field(
        name=f"{act.title()} By",
        value=interaction.user.mention,
        inline=False,
    )

    embed.add_field(
        name="Reason",
        value=f"- {reason}",
        inline=False,
    )

    return embed

def build_staff_batch_update_embed(
    ctx: commands.Context,
    descriptions: list[str],
    update_type: str,
    reason: str,
) -> discord.Embed:

    act = "promoted" if update_type == "promotion" else "demoted"

    embed = discord.Embed(
        color=0xFFFFFF,
        title=f"{update_type.title()} Information",
        description="\n".join(descriptions) if descriptions else "No updates processed."
    )

    embed.set_image(url=img["border"])

    embed.add_field(
        name=f"{act.title()} By",
        value=ctx.author.mention,
        inline=False,
    )

    embed.add_field(
        name="Reason",
        value=f"- {reason}",
        inline=False,
    )

    return embed

def infraction_embed(moderator: discord.Member, reason: Optional[str], guild_name: str ,type: str) -> discord.Embed:
    embed = discord.Embed(
        color=16777215,
        title=f"{emoji['arrow']} A {type} has been issued to you",
    )
    embed.set_thumbnail(url=img['warn'])
    embed.add_field(
        name=f"{emoji['bookmark']} Reason",
        value=reason,
        inline=False,
    )

    """
    embed.add_field(
        name=f"{emoji["member"]} Issued by",
        value=moderator.mention
    )
    """
    embed.add_field(
        name=f"{emoji['bot']} Server",
        value=guild_name,
        inline=False,
    )

    return embed

def staff_remove_embed(moderator: discord.Member, reason: Optional[str], guild_name: str) -> discord.Embed:
    embed = discord.Embed(
        color=16777215,
        title=f"{emoji['arrow']} You Have Been removed from the Staff Team!",
    )
    embed.set_thumbnail(url=img['warn'])
    embed.add_field(
        name=f"{emoji['bookmark']} Reason",
        value=reason,
        inline=False,
    )

    embed.add_field(
        name=f"{emoji["member"]} Removed by",
        value=moderator.mention
    )
    embed.add_field(
        name=f"{emoji['bot']} Server",
        value=guild_name,
        inline=False,
    )

    return embed

def loa_accept_embed(accepted_by: int, guild_name: str) -> discord.Embed:
    embed = discord.Embed(
        color=16777215,
        title=f"{emoji['arrow']} Your LOA has been accepted!",
    )

    embed.set_thumbnail(url=img['warn'])
    embed.add_field(
        name=f"{emoji["member"]} Accepted by",
        value=f'<@{accepted_by}>'
    )
    embed.add_field(
        name=f"{emoji['bot']} Server",
        value=guild_name,
        inline=False,
    )

    return embed

def loa_reject_embed(rejected_by: int, guild_name: str, reason: str) -> discord.Embed:
    embed = discord.Embed(
        color=16777215,
        title=f"{emoji['arrow']} Your LOA has been Rejected!",
    )

    embed.set_thumbnail(url=img['warn'])
    embed.add_field(
        name=f"{emoji["member"]} Rejected by",
        value=f'<@{rejected_by}>',
        inline=False
    )
    embed.add_field(
        name=f"{emoji['bookmark']} Reason",
        value=reason,
        inline=False,
    )
    embed.add_field(
        name=f"{emoji['bot']} Server",
        value=guild_name,
        inline=False,
    )

    return embed

def staff_strike_remove_embed(
    removed_by: discord.Member,
    moderator: int,
    reason: Optional[str],
    guild_name: str
) -> discord.Embed:
    
    embed = discord.Embed(
        color=16777215,
        title=f"{emoji['arrow']} A strike has been removed!",
        description=(
            f"- A strike which was issued to you previously "
            f"has been removed!"
        )
    )

    embed.add_field(
        name=f"{emoji['member']} Strike Removed By",
        value=removed_by.mention,
        inline=False
    )

    embed.add_field(
        name=f"{emoji['bookmark']} Strike Reason",
        value=reason or "No reason provided.",
        inline=False
    )

    embed.add_field(
        name=f"{emoji['bot']} Server",
        value=guild_name,
        inline=False
    )

    embed.set_thumbnail(url=img['warn'])

    return embed