from typing import Optional

import discord
from discord.ext import commands, tasks
from datetime import timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core.utils import lily_utility as LilyUtility
from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.features.permissions.lily_permissions import permission
from src.core.features.management.controller import lily_management_controller as controller
from src.core.features.management.components.staff_management_components import LOARequestView
from src.core.features.management.controller.lily_management_controller import (
    automatic_quota_evaluator,
)

from .groups import *


class LilyManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db: Optional[BotGlobalsDatabaseAccess] = None
        self.scheduler = AsyncIOScheduler(timezone="UTC")

        self.staff_group = StaffCommands()
        self.infraction_group = InfractionCommands()
        self.loa_group = LoaCommands()
        self.rank_group = RankCommands()
        self.quota_group = QuotaCommands()
        self.dev_group = DevCommands()
        self.staff_role_group = StaffRoleCommands()

        self.message_reset_schedular.start()

    @property
    def _command_groups(self):
        return (
            self.staff_group,
            self.infraction_group,
            self.loa_group,
            self.rank_group,
            self.quota_group,
            self.dev_group,
            self.staff_role_group,
        )

    async def cog_load(self) -> None:
        for group in self._command_groups:
            self.bot.tree.add_command(group)

    async def cog_unload(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        for group in self._command_groups:
            self.bot.tree.remove_command(group.name)

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





    """ Certain Commands exposed as prefix for convenience  """
    @commands.group(name="staff", invoke_without_command=True, aliases=["stf", "st"])
    async def staff(self, ctx: commands.Context):
        pass

    @staff.command(name="data")
    @permission(command_name="staff_data")
    async def staff_data(self, ctx: commands.Context, user: discord.Member | discord.User | None = None):
        if not user:
            user = ctx.author
        await controller.fetch_staff_detail(ctx, user)


    @staff.command(name="list")
    @permission(command_name="staff_list")
    async def staff_list(self, ctx: commands.Context):
        await controller.fetch_all_staffs(ctx=ctx)



async def setup(bot):
    cog = LilyManagement(bot)
    await bot.add_cog(cog)

    if hasattr(cog, "on_load"):
        await cog.on_load()
