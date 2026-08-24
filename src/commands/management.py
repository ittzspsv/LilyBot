import re
import discord

from discord.ext import commands, tasks
from discord import app_commands
from datetime import timedelta
from zoneinfo import available_timezones
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core.features.permissions.lily_permissions import app_permission
from src.core.utils import lily_utility as LilyUtility
from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.features.management.types.staff_management_types import *
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.features.management.components.staff_management_components import LOARequestView, RankConfigureModal

from src.core.features.management.controller.lily_management_controller import (
    fetch_staff_detail,
    fetch_all_staffs,
    add_staff,
    remove_staff,
    edit_staff,
    strike_staff,
    remove_strike_staff,
    list_strikes,
    edit_strike,
    add_loa,
    remove_loa,
    list_loa,
    request_loa,
    loa_delete,
    get_all_staff_roles,
    update_staff,
    on_message,
    add_staff_quota,
    remove_staff_quota,
    fetch_staff_quota,
    check_staff_quota,
    remove_role,
    evaluate_staff_quota,
    get_staffs_timezone_coverage,
    automatic_quota_evaluator,
)


class LilyManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db: Optional[BotGlobalsDatabaseAccess] = None
        self.scheduler = AsyncIOScheduler(timezone="UTC")

        self.message_reset_schedular.start()

    async def timezone_autocomplete(self, interaction: discord.Interaction, current):
        matches = [
            tz for tz in sorted(available_timezones())
            if current.lower() in tz.lower()
        ]
        return [
            app_commands.Choice(name=tz, value=tz)
            for tz in matches[:25]
        ]

    async def on_load(self):
        self.db = self.bot.db

        """ Initialize all LOA views """
        if self.db is not None:
            rows = await self.db.fetch_all_loa_pending()
            for row in rows:
                try:
                    view = LOARequestView(
                        self.db,
                        row["staff_id"],
                        row["guild_id"],
                        row["staff_pfp"],
                        row["reason"],
                        row["days"]
                    )

                    self.bot.add_view(view, message_id=row["message_id"])
                except Exception as e:
                    print(f"Exception [LOARequestView] {e}")
                    continue
            print("LOA Views Initialized!")

        """ Start the cron schedular """
        self.scheduler.add_job(
            self._run_daily,
            CronTrigger(hour=23, minute=55),
            id="quota_daily",
            misfire_grace_time=3600,
            coalesce=True,
            replace_existing=True
        )
        self.scheduler.add_job(
            self._run_weekly,
            CronTrigger(day_of_week="sun", hour=23, minute=55),
            id="quota_weekly",
            misfire_grace_time=3600,
            coalesce=True,
            replace_existing=True
        )
        self.scheduler.add_job(
            self._run_monthly,
            CronTrigger(day="last", hour=23, minute=55),
            id="quota_monthly",
            misfire_grace_time=3600,
            coalesce=True,
            replace_existing=True
        )
        self.scheduler.start()

    async def cog_unload(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def _run_daily(self):
        if self.bot.db is None:
            return
        await automatic_quota_evaluator("1d", self.bot)

    async def _run_weekly(self):
        if self.bot.db is None:
            return
        await automatic_quota_evaluator("7d", self.bot)

    async def _run_monthly(self):
        if self.bot.db is None:
            return
        await automatic_quota_evaluator("30d", self.bot)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.db is None:
            return
        await on_message(message, self.db)

    @tasks.loop(minutes=5)
    async def message_reset_schedular(self):
        if self.bot.db is None:
            return

        now = LilyUtility.utcnow()

        row = await self.bot.db.fetch_one(
            "SELECT next_day_update, next_week_update, next_month_update FROM updates"
        )

        if not row:
            return

        next_day, next_week, next_month = map(LilyUtility.parse_date, row)

        if next_day and now >= next_day:
            await self.daily_callback()

            new_day = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            await self.bot.db.execute(
                "UPDATE updates SET next_day_update = ?", 
                (LilyUtility.iso(new_day),),
                commit=True
            )

        if next_week and now >= next_week:
            await self.weekly_callback()

            days_ahead = 7 - now.weekday()
            if days_ahead == 0:
                days_ahead = 7

            new_week = (now + timedelta(days=days_ahead)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            await self.bot.db.execute(
                "UPDATE updates SET next_week_update = ?", 
                (LilyUtility.iso(new_week),),
                commit=True
            )

        if next_month and now >= next_month:
            await self.monthly_callback()

            if now.month == 12:
                new_month = now.replace(year=now.year + 1, month=1, day=1)
            else:
                new_month = now.replace(month=now.month + 1, day=1)

            new_month = new_month.replace(hour=0, minute=0, second=0, microsecond=0)

            await self.bot.db.execute(
                "UPDATE updates SET next_month_update = ?", 
                (LilyUtility.iso(new_month),),
                commit=True
            )

    async def daily_callback(self):
        if self.db is None:
            return

        await self.db.reset_messages("daily")

    async def weekly_callback(self):
        if self.db is None:
            return
        
        await self.db.reset_messages("weekly")

    async def monthly_callback(self):
        if self.db is None:
            return
        
        await self.db.reset_messages("monthly")

    staff = app_commands.Group(
        name="staff",
        description="Staff management commands"
    )

    infraction = app_commands.Group(
        name="infraction",
        description="Infraction management commands"
    )

    loa = app_commands.Group(
        name="loa",
        description="Leave of absence management"
    )

    rank = app_commands.Group(
        name="rank",
        description="Promotion and demotion commands"
    )

    quota = app_commands.Group(
        name="quota",
        description="Quota management commands"
    )

    dev = app_commands.Group(
        name="dev",
        description="Developer utility commands"
    )

    staff_role = app_commands.Group(
        name="staff_role",
        description="Staff Management role utility commands"
    )


    @staff.command(name='data', description='shows data for a particular staff')
    @app_permission(command_name="staff_data")
    @app_commands.guild_only()
    async def staff_data(self, interaction: discord.Interaction, user: discord.Member| discord.User | None = None):
        if not user:
            user = interaction.user
        await fetch_staff_detail(interaction, user)

    @staff.command(name='list', description='shows all staff registered name with the count')
    @app_permission(command_name="staff_list")
    @app_commands.guild_only()
    async def staffs(self, interaction: discord.Interaction):
        await fetch_all_staffs(interaction)


    @infraction.command(name='issue', description='Issue an infraction')
    @app_permission(command_name="strike_add")
    @app_commands.guild_only()
    async def staffstrike(self, interaction: discord.Interaction, staff: discord.Member):
        await strike_staff(interaction, staff)

    @infraction.command(name='remove', description='Remove an infraction')
    @app_permission(command_name="strike_remove")
    @app_commands.guild_only()
    async def removestrike(self, interaction: discord.Interaction, infraction_id: str):
        await remove_strike_staff(interaction, int(infraction_id))

    @infraction.command(name="edit", description="Edit a reason of a infraction")
    @app_permission(command_name="strike_edit")
    @app_commands.guild_only()
    async def strike_edit(self, interaction: discord.Interaction, infraction_id: str, new_reason: str):
        await edit_strike(interaction, int(infraction_id), new_reason)

    @staff.command(name='edit', description='edits a staff data')
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    @app_permission(command_name="staff_edit")
    @app_commands.guild_only()
    async def EditStaff(self, interaction: discord.Interaction, staff: discord.Member | discord.User, name: str , joined_on: str | None = None, timezone: str | None = None,responsibility: str | None = None):
        await edit_staff(interaction, staff.id, name, joined_on, timezone, responsibility)

    @staff.command(name="self_edit", description="edits your staff data")
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    @app_permission(command_name="staff_self_edit")
    @app_commands.guild_only()
    async def self_edit_staff_data(self, interaction: discord.Interaction, name: str, timezone: str | None =None):
        await edit_staff(interaction, interaction.user.id, name, None, timezone, None)

    @infraction.command(name='show', description='shows infractions for a concurrent staff')
    @app_permission(command_name="strike_show")
    @app_commands.guild_only()
    async def strikes(self, interaction: discord.Interaction, staff: discord.Member):
        await list_strikes(interaction, staff)

    @staff.command(name='add', description='Adds a member to staff_data')
    @app_permission(command_name="staff_add")
    @app_commands.guild_only()
    async def add_staff(self, interaction: discord.Interaction, staff: discord.Member):
        await add_staff(interaction, staff)

    @staff.command(name='remove', description='Removes a member from staff_data')
    @app_permission(command_name="staff_remove")
    @app_commands.guild_only()
    async def remove_staff(self, interaction: discord.Interaction, staff: discord.Member | discord.User, reason: str):
        await remove_staff(interaction, staff, reason)


    @staff.command(name='roles', description='Returns all staff roles')
    @app_permission(command_name="staff_roles")
    @app_commands.guild_only()
    async def get_all_staff_roles(self, interaction: discord.Interaction):
        await get_all_staff_roles(interaction)


    @loa.command(name='add', description='Assigns a staff leave')
    @app_permission(command_name="loa_add")
    @app_commands.guild_only()
    async def add_loa(self, interaction: discord.Interaction, staff: discord.Member, *, reason: str):
        await add_loa(interaction, staff, reason)

    @loa.command(name='delete', description='Delete an LOA entry from the database')
    @app_permission(command_name="loa_delete")
    @app_commands.guild_only()
    async def loa_delete(self, interaction: discord.Interaction, leave_id: int):
        await loa_delete(interaction, leave_id)

    @loa.command(name='remove', description='Removes a staff leave')
    @app_permission(command_name="loa_remove")
    @app_commands.guild_only()
    async def remove_loa(self, interaction: discord.Interaction, staff: discord.Member):
        await remove_loa(interaction, staff)

    @loa.command(name="show", description="List all LOA for a particular staff")
    @app_permission(command_name="loa_show")
    @app_commands.guild_only()
    async def show_loa(self, interaction: discord.Interaction, staff: discord.Member | None =None):
        if staff is None:
            current_staff = interaction.user
        else:
            current_staff = staff

        if isinstance(current_staff, discord.Member):
            await list_loa(interaction, current_staff)

    @loa.command(name="request", description="Request LOA")
    @app_permission(command_name="loa_request")
    @app_commands.guild_only()
    async def request_loa(self, interaction: discord.Interaction):
        await request_loa(interaction)

    @rank.command(name='promote', description='Promotes a staff to upper rank')
    @app_permission(command_name="rank_promote")
    @app_commands.guild_only()
    async def promote(self, interaction: discord.Interaction, staff: discord.Member, * ,reason: str):
        await update_staff(interaction, staff, reason, "promotion")
    
    @rank.command(name='demote', description='Demotes a staff to lower rank')
    @app_permission(command_name="rank_demote")
    @app_commands.guild_only()
    async def demote(self, interaction: discord.Interaction, staff: discord.Member, *, reason: str):
        await update_staff(interaction, staff, reason, "demotion")

    @quota.command(name="add", description="Adds a staff quota to check by")
    @app_permission(command_name="quota_add")
    @app_commands.guild_only()
    async def add_quota(self, interaction: discord.Interaction, quota_role: discord.Role, minimum_ms: int, minimum_msg: int, check_by: QuotaCheckBy):
        await add_staff_quota(interaction, quota_role, minimum_ms, minimum_msg, check_by)

    @quota.command(name="list", description="List all defined quotas for this server")
    @app_permission(command_name="quota_list")
    @app_commands.guild_only()
    async def list_quota(self, interaction: discord.Interaction):
        await fetch_staff_quota(interaction)

    @quota.command(name="remove", description="Remove a defined quota by its ID")
    @app_permission(command_name="quota_remove")
    @app_commands.guild_only()
    async def remove_quota(self, interaction: discord.Interaction, quota_id: str):
        await remove_staff_quota(interaction, quota_id)

    @quota.command(name="check", description="Check quota for a given staff")
    @app_permission(command_name="quota_check")
    @app_commands.guild_only()
    async def check_quota(self, interaction: discord.Interaction, staff: discord.Member | None = None):
        staff_member = staff or interaction.user
        await check_staff_quota(interaction, staff_member)


    @quota.command(name="evaluate", description="Evaluates Staff quota and updates the results")
    @app_permission(command_name="quota_evaluate")
    @app_commands.guild_only()
    async def evaluate_staff_quota(self, interaction: discord.Interaction, role: discord.Role):
        await evaluate_staff_quota(interaction, role)
        
    @staff_role.command(name="remove", description="Removes a staff role from the database")
    @app_permission(command_name="staff_role_remove")
    @app_commands.guild_only()
    async def remove_role(self, interaction: discord.Interaction, role: discord.Role):
        await remove_role(interaction, role.id)

    @staff_role.command(name="remove_raw", description="Removes a staff role from the database")
    @app_permission(command_name="staff_role_remove_raw")
    @app_commands.guild_only()
    async def remove_role_raw(self, interaction: discord.Interaction, role: str):
        await remove_role(interaction, int(role))

    @rank.command(name="configure", description="Configure staff ranks")
    @app_permission(command_name="rank_configure")
    @app_commands.guild_only()
    async def rank_configure(self, interaction: discord.Interaction):
        bot_db: BotGlobalsDatabaseAccess = self.bot.db

        assert interaction.guild is not None

        try:
            staff_ranks = await bot_db.get_staff_ranks(interaction.guild.id)
            await interaction.response.send_modal(
                RankConfigureModal(bot_db, staff_ranks)
            )
        except Exception as e:
            print(e)

    @staff.command(name="coverage", description="get the timezone coverage of all the staffs")
    @app_permission(command_name="staff_coverage")
    @app_commands.guild_only()
    async def staff_coverage(self, interaction: discord.Interaction):
        await get_staffs_timezone_coverage(interaction)

async def setup(bot):
    cog = LilyManagement(bot)
    await bot.add_cog(cog)

    if hasattr(cog, "on_load"):
        await cog.on_load()