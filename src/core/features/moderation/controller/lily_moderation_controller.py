from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, cast

import discord
from discord.ext import commands
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from src.core.database.integrations.bot_globals import BanLimitStatus
from src.core.features.moderation.components.sLilyModerationComponents import *
from src.core.features.moderation.utils.moderation_utils import mute_parser
from src.core.features.permissions.lily_permissions import has_app_permission
from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.utils.lily_utility import utcnow

from ....utils.components.sLIlyGlobalComponents import CommandInfo

if TYPE_CHECKING:
    from src.lily import Lily

""" Ban / Quarantine command helpers """
async def _validate_moderation_target(
    ctx: commands.Context | discord.Interaction,
    user_input: discord.User | discord.Member
) -> Optional[Tuple[discord.Member | discord.User, BanLimitStatus, List[int]]]:

    if isinstance(ctx, commands.Context):
        bot = cast("Lily", ctx.bot)
        author = ctx.author
    else:
        bot = cast("Lily", ctx.client)
        author = ctx.user

    if ctx.guild is None:
        await bot.send(ctx, embed=simple_embed("Command requires a guild object to execute.", "cross"))
        return None

    if not isinstance(author, discord.Member):
        await bot.send(ctx, embed=simple_embed("Please execute this command inside a guild!", "cross"))
        return None

    user_id = user_input.id
    if not user_id:
        await bot.send(ctx, embed=simple_embed("Invalid user.", "cross"))
        return None

    member: discord.Member | discord.User = user_input

    if isinstance(member, discord.Member):
        if member.id == author.id:
            await bot.send(ctx, embed=simple_embed("You cannot moderate yourself.", "cross"))
            return None

        assert bot.user is not None
        if member.id == bot.user.id:
            await bot.send(ctx, embed=simple_embed("You cannot moderate me baka~.", "cross"))
            return None

        if member.id == ctx.guild.owner_id:
            await bot.send(ctx, embed=simple_embed("You cannot moderate the server owner.", "cross"))
            return None

        if member.top_role >= ctx.guild.me.top_role:
            await bot.send(ctx, embed=simple_embed(
                "I cannot act on this user their role is higher than or equal to mine.", "cross"
            ))
            return None

        if member.top_role >= author.top_role:
            await bot.send(ctx, embed=simple_embed(
                "You cannot act on this user their role is higher than or equal to yours.", "cross"
            ))
            return None

    author_roles = [role.id for role in author.roles if role.name != "@everyone"]
    assert bot.db is not None
    status = await bot.db.get_ban_limit_status(ctx.guild.id, author.id, author_roles)

    if status.exceeded:
        await bot.send(ctx, embed=simple_embed(
            f"Daily limit exceeded.\n{status.remaining_time}", "cross"
        ))
        return None

    return member, status, author_roles

async def ban_user(
    ctx: commands.Context | discord.Interaction,
    user_input,
    reason="No reason provided",
    proofs: list = []
):
    if isinstance(ctx, commands.Context):
        bot = cast("Lily", ctx.bot)
        author = ctx.author
    else:
        bot = cast("Lily", ctx.client)
        author = ctx.user

    assert bot.db is not None
    assert bot.logging_controller is not None

    logging_controller = bot.logging_controller

    if ctx.guild is None:
        await bot.send(ctx, embed=simple_embed("This command can only be executed inside an guild", 'cross'))
        return

    if not isinstance(author, discord.Member):
        await bot.send(ctx, embed=simple_embed("Command requires member object inorder to execute", 'cross'))
        return

    assert isinstance(ctx.guild, discord.Guild)

    """ Validate the target first """
    result = await _validate_moderation_target(ctx, user_input)
    if result is None:
        return
    member, status, author_roles = result

    await ctx.guild.ban(
        discord.Object(id=member.id),
        reason=f"By {author} | {reason}",
    )
    ban_message: str = f"Banned: <@{member.id}>\n**Remaining:** {max(0, status.remaining_count - 1)}"

    if proofs:
        await bot.send(ctx, embed=simple_embed(ban_message))
        await logging_controller.log_moderation_action(
            ctx, author, member, "ban", reason, proofs.copy()
        )
    else:
        case_id = await logging_controller.log_moderation_action(
            ctx, author, member, "ban", reason, proofs.copy()
        )
        if case_id:
            view = CaseProofsView(case_id, logging_controller, None)
            msg = await bot.send(ctx, embed=simple_embed(ban_message), view=view)
            view.message = msg
        else:
            await bot.send(ctx, embed=simple_embed(ban_message))

async def quarantine_user(
    ctx: commands.Context | discord.Interaction,
    user_input: discord.User | discord.Member,
    reason="No reason provided",
    proofs: list = []
):
    if isinstance(ctx, commands.Context):
        bot = cast("Lily", ctx.bot)
    else:
        bot = cast("Lily", ctx.client)


    if ctx.guild is None:
        await bot.send(ctx, embed=simple_embed("This command can only be executed inside an guild", 'cross'))
        return

    assert isinstance(ctx.guild, discord.Guild)
    assert bot.logging_controller is not None
    logging_controller = bot.logging_controller

    result = await _validate_moderation_target(ctx, user_input)
    if result is None:
        return
    member, status, author_roles = result

    if not isinstance(member, discord.Member):
        await bot.send(ctx, embed=simple_embed("User should be in the guild inorder to quarantine them", 'cross'))
        return

    quarantine_role = (
        discord.utils.get(ctx.guild.roles, name="Quarantine")
        or discord.utils.get(ctx.guild.roles, name="Prisoner")
    )

    if not quarantine_role or quarantine_role >= ctx.guild.me.top_role:
        return await bot.send(ctx, embed=simple_embed("Quarantine role issue.", "cross"))

    if quarantine_role in member.roles:
        return await bot.send(ctx, embed=simple_embed("Already quarantined.", "cross"))

    author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
    await member.add_roles(quarantine_role, reason=f"Quarantine by {author} | {reason}")

    quarantine_message: str = f"Quarantined: <@{member.id}>\n**Remaining:** {max(0, status.remaining_count - 1)}"
    if proofs:
        await bot.send(ctx, embed=simple_embed(quarantine_message))
        await logging_controller.log_moderation_action(
            ctx, author, member, "quarantine", reason, proofs.copy()
        )
    else:
        case_id = await logging_controller.log_moderation_action(
            ctx, author, member, "quarantine", reason, proofs.copy()
        )
        if case_id:
            view = CaseProofsView(case_id, logging_controller, None)
            msg = await bot.send(ctx, embed=simple_embed(quarantine_message), view=view)
            view.message = msg
        else:
            await bot.send(ctx, embed=simple_embed(quarantine_message))

async def mute_user(
    ctx: commands.Context | discord.Interaction,
    user: discord.Member | discord.User,
    duration: str,
    reason: str = "No reason provided",
    proofs: list = []
):
    if isinstance(ctx, commands.Context):
        bot = cast("Lily", ctx.bot)
        author = ctx.author
    else:
        bot = cast("Lily", ctx.client)
        author = ctx.user

    if ctx.guild is None:
        await bot.send(ctx, embed=simple_embed("Command requires guild object inorder to execute", 'cross'))
        return

    if not isinstance(author, discord.Member):
        await bot.send(ctx, embed=simple_embed("Command requires member object inorder to execute", 'cross'))
        return

    assert bot.user is not None
    if user.id == bot.user.id:
        await bot.send(ctx, embed=simple_embed("You cannot mute me baka~.", "cross"))
        return

    if isinstance(user, discord.User):
        await bot.send(ctx, embed=simple_embed("The user has left the server", 'cross'))
        return

    if user.timed_out_until and user.timed_out_until > discord.utils.utcnow():
        await bot.send(ctx, embed=simple_embed("This user is already muted", 'cross'))
        return

    if user.top_role >= ctx.guild.me.top_role:
        await bot.send(ctx, embed=simple_embed("I cannot mute this user", 'cross'))
        return

    if user.top_role >= author.top_role:
        await bot.send(ctx, embed=simple_embed("I cannot mute a user with a role equal to or higher than yours.", 'cross'))
        return

    if user.id in {ctx.guild.owner_id}:
        await bot.send(ctx, embed=simple_embed("You cannot mute the server owner", 'cross'))
        return

    if user.id == author.id:
        await bot.send(ctx, embed=simple_embed("You cannot mute yourself.", 'cross'))
        return

    assert bot.logging_controller is not None

    logging_controller = bot.logging_controller

    try:
        seconds = mute_parser(duration)
        until = utcnow() + timedelta(seconds=seconds)

        await user.edit(timed_out_until=until, reason=reason)

        if len(proofs) > 0:
            await bot.send(ctx, embed=simple_embed(
                f"Muted: <@{user.id}>"
            ))

        case_id: int | None = await logging_controller.log_moderation_action(ctx, author, user, "mute", reason, proofs, {"duration": seconds})

        if case_id and len(proofs) <= 0:
            view = CaseProofsView(case_id, logging_controller, None)
            msg = await bot.send(
                ctx,
                embed=simple_embed(
                    f"Muted: <@{user.id}>"
                ),
                view=view
            )

            view.message = msg

    except ValueError as ve:
        await bot.send(ctx, embed=simple_embed(str(ve)))
    except discord.HTTPException as e:
        print(f"[MuteUser] {e}")
        await bot.send(ctx, embed=simple_embed("Failed to mute the user", 'cross'))
    except Exception as e:
        print(f"[MuteUser] {e}")
        await bot.send(ctx, embed=simple_embed("Failed to mute the user", 'cross'))

async def unmute(
    ctx: commands.Context | discord.Interaction,
    user: discord.Member | discord.User,
    reason: str = "No reason provided"
):
    if isinstance(ctx, commands.Context):
        bot = cast("Lily", ctx.bot)
        author = ctx.author
    else:
        bot = cast("Lily", ctx.client)
        author = ctx.user

    if not isinstance(author, discord.Member):
        await bot.send(ctx, embed=simple_embed("Command requires member object inorder to execute", 'cross'))
        return

    if isinstance(user, discord.User):
        await bot.send(ctx, embed=simple_embed("The user has left the server", 'cross'))
        return
    if not user.timed_out_until or user.timed_out_until <= discord.utils.utcnow():
        await bot.send(ctx, embed=simple_embed("That user is not muted currently", 'cross'))
        return

    assert bot.logging_controller is not None
    logging_controller = bot.logging_controller

    try:
        await user.edit(timed_out_until=None, reason=f"Manual unmute by moderator {author.mention}")
        await bot.send(ctx, embed=simple_embed(f"Unmuted: <@{user.id}>"))

        await logging_controller.log_moderation_action(
            ctx,
            author,
            user,
            "unmute",
            reason
        )

    except discord.HTTPException as e:
        await bot.send(ctx, embed=simple_embed(f"Failed to unmute user. {e}", 'cross'))
    except Exception as e:
        await bot.send(ctx, embed=simple_embed(f"Exception: {e}", 'cross'))

async def unban(
    ctx: commands.Context | discord.Interaction,
    user: discord.User,
    reason: str = "No reason provided"
):
    if isinstance(ctx, commands.Context):
        bot = cast("Lily", ctx.bot)
        author = ctx.author
    else:
        bot = cast("Lily", ctx.client)
        author = ctx.user

    if user is None:
        if isinstance(ctx, commands.Context):
            await ctx.reply(view=CommandInfo(ctx, "Unban", ["unban user", f"unban {ctx.me.mention} Appealed"]))
        return

    assert ctx.guild is not None

    assert bot.logging_controller is not None
    logging_controller = bot.logging_controller

    try:
        await ctx.guild.unban(user, reason=f"By {author} | {reason}")
        await bot.send(ctx, embed=simple_embed(f"Unbanned {user.mention}"))
        await logging_controller.log_moderation_action(
            ctx,
            author,
            user,
            "unban",
            reason
        )
    except discord.NotFound:
        await bot.send(ctx, embed=simple_embed("This user is not banned.", "cross"))
    except discord.Forbidden:
        await bot.send(ctx, embed=simple_embed("I don't have permission to unban this user.", "cross"))
    except discord.HTTPException as e:
        await bot.send(ctx, embed=simple_embed(f"Exception Raised: {e}", "cross"))

async def release(
    ctx: commands.Context | discord.Interaction,
    member: discord.Member | None = None,
    reason: str = "No reason provided"
):
    if isinstance(ctx, commands.Context):
        bot = cast("Lily", ctx.bot)
        author = ctx.author
    else:
        bot = cast("Lily", ctx.client)
        author = ctx.user

    if member is None:
        if isinstance(ctx, commands.Context):
            await ctx.reply(view=CommandInfo(ctx, "Release", ["release @user", f"release @user Appealed"]))
        return

    assert ctx.guild is not None

    assert bot.logging_controller is not None
    logging_controller = bot.logging_controller

    quarantine_role = (
        discord.utils.get(ctx.guild.roles, name="Quarantine")
        or discord.utils.get(ctx.guild.roles, name="Prisoner")
    )

    if not quarantine_role:
        await bot.send(ctx, embed=simple_embed("No Quarantine/Prisoner role found in this server.", "cross"))
        return

    if quarantine_role not in member.roles:
        await bot.send(ctx, embed=simple_embed(f"{member.mention} is not quarantined.", "cross"))
        return

    try:
        await member.remove_roles(quarantine_role, reason=f"By {author} | {reason}")
        await bot.send(ctx, embed=simple_embed(f"Released {member.mention} from quarantine."))
        await logging_controller.log_moderation_action(
            ctx,
            author,
            member,
            "quarantine_release",
            reason
        )
    except discord.Forbidden:
        await bot.send(ctx, embed=simple_embed("I don't have permission to remove the Quarantine role.", "cross"))
    except discord.HTTPException as e:
        await bot.send(ctx, embed=simple_embed(f"Failed to remove Quarantine role: {e}", "cross"))

async def warn(
    ctx: commands.Context | discord.Interaction,
    member: discord.Member | discord.User,
    reason: str,
    proofs=[]
):
    if isinstance(ctx, commands.Context):
        bot = cast("Lily", ctx.bot)
        author = ctx.author
    else:
        bot = cast("Lily", ctx.client)
        author = ctx.user

    if ctx.guild is None:
        await bot.send(ctx, embed=simple_embed("Command requires guild object inorder to execute", 'cross'))
        return

    if not isinstance(author, discord.Member):
        await bot.send(ctx, embed=simple_embed("Command requires member object inorder to execute", 'cross'))
        return

    if isinstance(member, discord.User):
        await bot.send(ctx, embed=simple_embed("The user has left the server", 'cross'))
        return

    assert bot.user is not None
    if member.id == bot.user.id:
        await bot.send(ctx, embed=simple_embed("You cannot warn me baka~.", "cross"))
        return

    if member.top_role >= ctx.guild.me.top_role:
        await bot.send(ctx, embed=simple_embed("I cannot warn this user", 'cross'))
        return

    if member.top_role >= author.top_role:
        await bot.send(ctx, embed=simple_embed("I cannot warn a user with a role equal to or higher than yours.", 'cross'))
        return

    assert bot.logging_controller is not None
    logging_controller = bot.logging_controller

    if len(proofs) > 0:
        await bot.send(ctx, embed=simple_embed(f"{member.mention} has been warned"))

    case_id: int | None = await logging_controller.log_moderation_action(ctx, author, member, "warn", reason, proofs)

    if case_id and len(proofs) <= 0:
        view = CaseProofsView(case_id, logging_controller, None)
        msg = await bot.send(ctx, embed=simple_embed(f"{member.mention} has been warned"), view=view)
        view.message = msg

async def case_edit(
    interaction: discord.Interaction,
    case_id: int,
    case_statement: str,
    absolute: bool = False
):
    bot = cast("Lily", interaction.client)

    assert bot.db is not None
    bot_db = bot.db

    response = await bot_db.edit_case(**{"staff_id": interaction.user.id, "case_id": case_id, "case_statement": case_statement, "absolute": absolute})

    if response.get("success"):
        await interaction.response.send_message(embed=simple_embed(str(response.get("message"))))
    else:
        await interaction.response.send_message(embed=simple_embed(str(response.get("message")), 'cross'))

async def case_delete(
    interaction: discord.Interaction,
    case_id: int
):
    bot = cast("Lily", interaction.client)

    assert bot.db is not None
    bot_db = bot.db

    response = await bot_db.delete_case(case_id)
    if response.get("success"):
        await interaction.response.send_message(embed=simple_embed(str(response.get("message"))))
    else:
        await interaction.response.send_message(embed=simple_embed(str(response.get("message")), 'cross'))

async def ms(
    interaction: discord.Interaction,
    moderator: discord.Member | discord.User,
    page_start: int = 0,
    page_end: int = 5
):
    bot = cast("Lily", interaction.client)

    assert bot.db is not None
    bot_db = bot.db

    if interaction.guild is None:
        await interaction.response.send_message(
            embed=simple_embed(
                "Command requires guild object in order to execute",
                "cross"
            )
        )
        return

    result = await bot_db.fetch_mod_stats(
        guild_id=interaction.guild.id,
        moderator_id=moderator.id,
        page_start=page_start,
        page_end=page_end
    )

    if not result["success"]:
        await interaction.response.send_message(embed=simple_embed("No stats found For the given moderator ID"))
        return

    embeds = build_ms_embed(
        moderator=moderator,
        logs=result["logs"],
        stats=result["stats"],
        total_logs=result["total_logs"],
        page_start=page_start
    )

    await interaction.response.send_message(embeds=embeds)

async def mod_logs(
    interaction: discord.Interaction,
    target_user_id: int,
    user: discord.Member | discord.User,
    moderator: discord.User | discord.Member | None = None,
    mod_type: str = "all"
):
    if interaction.guild is None:
        await interaction.response.send_message(
            embed=simple_embed(
                "Command requires guild object in order to execute",
                "cross"
            )
        )
        return

    bot = cast("Lily", interaction.client)
    assert bot.db is not None
    bot_db = bot.db

    payload = {
        "guild_id": interaction.guild.id,
        "target_user_id": target_user_id,
        "moderator_id": moderator.id if moderator else None,
        "mod_type": mod_type
    }

    result = await bot_db.fetch_mod_logs(**payload)

    if not result["success"]:
        await interaction.response.send_message(embed=simple_embed("No cases found.", 'cross'))
        return

    view = CaseListView((user.display_name.title(), user.display_avatar.url), result, bot_db)
    await interaction.response.send_message(view=view, allowed_mentions=discord.AllowedMentions.none())

async def moderation_insights(
    interaction: discord.Interaction
):
    if interaction.guild is None:
        await interaction.response.send_message(
            embed=simple_embed(
                "Command requires guild object in order to execute",
                "cross"
            )
        )
        return

    bot = cast("Lily", interaction.client)

    assert bot.db is not None
    bot_db = bot.db

    await interaction.response.defer()

    """ Create an image of moderation last 30 days analytics using matplotlib """
    data = await bot_db.get_moderation_monthly_analysis(interaction.guild.id)
    days = [
        datetime.strptime(item["day"], "%Y-%m-%d")
        for item in data
    ]

    totals = [
        item["total"]
        for item in data
    ]

    x_date = mdates.date2num(days)

    plt.figure(figsize=(12, 5))

    plt.plot(
        x_date,
        totals,
        marker="o",
        linewidth=2
    )

    plt.title("Moderation Actions - Last 30 Days")
    plt.xlabel("Date")
    plt.ylabel("Actions")

    plt.xticks(rotation=45)

    plt.grid(True, alpha=0.3)

    for x, y in zip(x_date, totals):
        plt.text(
            x,
            y,
            str(y),
            ha="center",
            va="bottom"
        )

    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(
        buffer,
        format="png",
        dpi=300,
        bbox_inches="tight"
    )

    buffer.seek(0)
    plt.close()

    """ Returns the total, monthly, weekly, daily modlogs in a server """
    view = ModerationInsights(interaction.guild.me, bot_db)
    view.message = await interaction.followup.send(view=view, file=discord.File(buffer, filename="moderation_analytics.png"))

async def setup_mod_appeal(
    interaction: discord.Interaction
):
    if interaction.guild is None:
        return

    me = interaction.guild.me

    bot = cast("Lily", interaction.client)

    assert bot.db is not None
    bot_db = bot.db

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(
            view_channel=False,
        ),

        me: discord.PermissionOverwrite(
            view_channel=True,
            manage_channels=True,
            manage_threads=True,
            send_messages=True,
            read_message_history=True,
        ),

        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            send_messages_in_threads=True,
            attach_files=True,
            embed_links=True,
            add_reactions=True,
            use_external_emojis=True,
            use_external_stickers=True,
        ),
    }

    try:
        forum = await interaction.guild.create_forum(
            name="moderation-appeal",
            available_tags=[
                discord.ForumTag(name="Pending", emoji="⏳"),
                discord.ForumTag(name="Accepted", emoji="✅"),
                discord.ForumTag(name="Denied", emoji="❌"),
            ],
            overwrites=overwrites,
            reason=f"Moderation appeal forum created by {interaction.user}",
        )

        await bot_db.set_channel(
            interaction.guild.id,
            forum.id,
            "moderation_appeal"
        )

        await bot_db.upsert_appeal_forum(
            interaction.guild.id,
            """
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

        webhook = await forum.create_webhook(
            name="Lily Webhook"
        )

        await bot_db.set_webhook(
            interaction.guild.id,
            "moderation_appeal_dm",
            webhook.url
        )

        await interaction.response.send_message(
            embed=simple_embed(
                f"Successfully created Appeal forums {forum.mention}.  Appeals will be posted on that forums\nPlease do not delete the `Pending` Tag from the forum"
            )
        )

    except discord.Forbidden:
        raise discord.app_commands.CheckFailure(
            "I don't have permission to create forum channels."
        )

    except discord.HTTPException as e:
        raise discord.app_commands.CheckFailure(
            f"Failed to create the moderation appeal forum: {e}"
        )

async def accept_appeal(
    interaction: discord.Interaction
):
    if interaction.guild is None:
        return

    bot = cast("Lily", interaction.client)
    assert bot.db is not None
    bot_db = bot.db

    if not isinstance(interaction.channel, discord.Thread):
        return await interaction.response.send_message(
            embed=simple_embed(
                "Unable to accept an invalid instigator appeal.",
                "cross",
            ),
            delete_after=5,
        )

    appeal = await bot_db.get_appeal(interaction.channel.id)
    if appeal is None:
        return await interaction.response.send_message(
            embed=simple_embed(
                "Unable to accept an invalid instigator appeal.",
                "cross",
            ),
            delete_after=5,
        )
    if appeal["status"] != "pending":
        return await interaction.response.send_message(
            embed=simple_embed(
                "This appeal is no longer in a valid state for this action.",
                "cross",
            ),
            delete_after=5,
        )

    case = await bot_db.get_case(appeal["case_id"])

    if case is None:
        await interaction.response.send_message(embed=simple_embed("Unable to find the case", 'cross'))
        return

    moderator = case["moderator_id"]
    if (
        interaction.user.id != moderator
        and
        has_app_permission(interaction, "mod_appeal_management") is False
    ):
        await interaction.response.send_message(embed=simple_embed(f"This action has been denied.  Only <@{moderator}> can Initiate it.", 'cross'))
        return

    try:
        member = await interaction.guild.fetch_member(case["target_user_id"])
        if case["mod_type"] == "mute":
            await member.edit(timed_out_until=None, reason=f"Appeal accepted by {interaction.user.mention}")
            await bot_db.log_moderation_action(
                interaction.guild.id,
                interaction.user.id,
                member.id,
                "unmute",
                "Appealed"
            )

        elif case["mod_type"] == "quarantine":
            role = discord.utils.get(interaction.guild.roles, name="Quarantine")
            if role:
                await member.remove_roles(role, reason=f"Appeal accepted by {interaction.user.mention}")
                await bot_db.log_moderation_action(
                    interaction.guild.id,
                    interaction.user.id,
                    member.id,
                    "quarantine_release",
                    "Appealed"
                )

        await member.send(embed=simple_embed("Your appeal has been accepted and the action has been lifted"))
    except:
        pass

    assert isinstance(interaction.channel, discord.Thread)
    assert isinstance(interaction.channel.parent, discord.ForumChannel)
    accepted = discord.utils.get(interaction.channel.parent.available_tags, name="Accepted")

    if accepted is None:
        return

    await bot_db.set_appeal_status(appeal["case_id"], "accepted")
    await interaction.response.send_message(embed=simple_embed(f"Successfully Accepted the appeal and their punishment has been lifted.\n This thread will be archived."))
    await asyncio.sleep(2)
    await interaction.channel.edit(applied_tags=[accepted], locked=True, archived=True)

async def reject_appeal(
    interaction: discord.Interaction,
    reason: str | None = None
):
    if interaction.guild is None:
        return

    if not isinstance(interaction.channel, discord.Thread):
        return await interaction.response.send_message(
            embed=simple_embed(
                "Unable to reject an invalid instigator appeal.",
                "cross",
            ),
            delete_after=5,
        )

    bot = cast("Lily", interaction.client)
    assert bot.db is not None
    bot_db = bot.db

    appeal = await bot_db.get_appeal(interaction.channel.id)
    if appeal is None:
        return await interaction.response.send_message(
            embed=simple_embed(
                "Unable to reject an invalid instigator appeal.",
                "cross",
            ),
            delete_after=5,
        )

    if appeal["status"] != "pending":
        return await interaction.response.send_message(
            embed=simple_embed(
                "This appeal is no longer in a valid state for this action.",
                "cross",
            ),
            delete_after=5,
        )

    case = await bot_db.get_case(appeal["case_id"])

    if case is None:
        await interaction.response.send_message(embed=simple_embed("Unable to find the case", 'cross'))
        return

    moderator = case["moderator_id"]
    if (
        interaction.user.id != moderator
        and
        has_app_permission(interaction, "mod_appeal_management") is False
    ):
        await interaction.response.send_message(embed=simple_embed(f"This action has been denied.  Only <@{moderator}> can Initiate it.", 'cross'))
        return
    try:
        member = await interaction.guild.fetch_member(case["target_user_id"])
        await member.send(embed=simple_embed(f"Your appeal has been denied. Sorry\n- Reason: {reason or "No reason Provided"}", 'cross'))
    except:
        pass

    assert isinstance(interaction.channel, discord.Thread)
    assert isinstance(interaction.channel.parent, discord.ForumChannel)
    rejected = discord.utils.get(interaction.channel.parent.available_tags, name="Denied")

    if rejected is None:
        print("Tag is not found")
        return

    await bot_db.set_appeal_status(appeal["case_id"], "rejected")
    await interaction.response.send_message(embed=simple_embed(f"Successfully rejected the appeal, This thread will be archived!"))
    await asyncio.sleep(2)
    await interaction.channel.edit(applied_tags=[rejected], locked=True, archived=True)