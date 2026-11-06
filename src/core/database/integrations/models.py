from __future__ import annotations


from ...features.leveling.utils.lily_leveling_utils import *
from .models import *

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from math import ceil
from typing import Any, Collection, Generic, Literal, Optional, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


import json
import sqlite3


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total_count: int

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if self.page_size < 1:
            raise ValueError("page_size must be >= 1")

    @property
    def max_page(self) -> int:
        return max(1, ceil(self.total_count / self.page_size))

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.max_page


@dataclass(frozen=True, slots=True)
class Edit(Generic[T]):
    before: T
    after: T


@dataclass
class GlobalConfig:
    jail: int

@dataclass
class BanLimitStatus:
    exceeded: bool
    max_limit: int
    recent_ban_count: int
    remaining_count: int
    remaining_time: Optional[str]
    cooldown_breakdown: Optional[str]


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class GuildObject:
    id: int
    prefix: str = "."

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> GuildObject:
        return cls(id=row["guild_id"], prefix=row["prefix"] or ".")

@dataclass(frozen=True, slots=True)
class AFK:
    timestamp: Optional[str] = None
    display_name: Optional[str] = None
    reason: Optional[str] = None

    @property
    def since(self) -> Optional[datetime]:
        return parse_dt(self.timestamp)

    @property
    def elapsed(self) -> Optional[timedelta]:
        since = self.since
        return _now() - since if since else None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> AFK:
        return cls(
            timestamp=row["timestamp"],
            display_name=row["display_name"],
            reason=row["reason"],
        )

@dataclass(frozen=True, slots=True)
class Member:
    id: int
    guild: GuildObject
    name: Optional[str] = None
    timezone: Optional[str] = None
    prefix: Optional[str] = None
    avatar_url: Optional[str] = None
    afk: Optional[AFK] = None

    @property
    def mention(self) -> str:
        return f"<@{self.id}>"

    @property
    def is_afk(self) -> bool:
        return self.afk is not None

    @property
    def command_prefix(self) -> str:
        return self.prefix or self.guild.prefix

    @property
    def has_valid_timezone(self) -> bool:
        if not self.timezone:
            return False
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            return False
        return True

    @property
    def tzinfo(self) -> ZoneInfo:
        if self.has_valid_timezone:
            return ZoneInfo(self.timezone)  # type: ignore[arg-type]
        return ZoneInfo("UTC")

    def now(self) -> datetime:
        return datetime.now(self.tzinfo)

    def localize(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(self.tzinfo)

    @property
    def utc_offset_label(self) -> str:
        offset = self.now().utcoffset() or timedelta(0)
        minutes = int(offset.total_seconds() // 60)
        sign = "+" if minutes >= 0 else "-"
        hours, mins = divmod(abs(minutes), 60)
        return f"UTC{sign}{hours:02d}:{mins:02d}"

    @classmethod
    def from_row(
        cls, row: sqlite3.Row, guild: GuildObject, afk: Optional[AFK] = None
    ) -> Member:
        return cls(
            id=row["member_id"],
            guild=guild,
            name=row["name"],
            timezone=row["timezone"],
            prefix=row["prefix"],
            avatar_url=row["avatar_url"],
            afk=afk,
        )

@dataclass(frozen=True, slots=True)
class Role:
    id: int
    guild_id: int
    name: Optional[str] = None
    ban_limit: Optional[int] = None
    ban_queue: bool = False
    role_assignment_scope: Literal["all", "specific", "except", "none"] = "none"
    role_type: str = "default"
    assignment_roles: frozenset[int] = frozenset()

    @property
    def mention(self) -> str:
        return f"<@&{self.id}>"

    def can_assign(self, target_role_id: int, targets: Collection[int]) -> bool:
        scope = self.role_assignment_scope
        if scope == "all":
            return True
        if scope == "specific":
            return target_role_id in targets
        if scope == "except":
            return target_role_id not in targets
        return False

    @classmethod
    def from_row(cls, row: sqlite3.Row, assignment_roles: Collection[int] = ()) -> Role:
        return cls(
            id=row["role_id"],
            guild_id=row["guild_id"],
            name=row["role_name"],
            ban_limit=row["ban_limit"],
            ban_queue=bool(row["ban_queue"]),
            role_assignment_scope=row["assignment_scope"] or "none",
            role_type=row["role_type"] or "default",
            assignment_roles=frozenset(assignment_roles),
        )

@dataclass(frozen=True, slots=True)
class Staff:
    id: int
    guild_id: int
    name: str
    joined_on: Optional[str] = None
    on_loa: bool = False
    retired: bool = False
    stale: bool = False
    responsibility: Optional[str] = None
    avatar_url: Optional[str] = None

    @property
    def mention(self) -> str:
        return f"<@{self.id}>"

    @property
    def is_active(self) -> bool:
        return not (self.retired or self.on_loa)

    @property
    def joined(self) -> Optional[datetime]:
        if not self.joined_on:
            return None
        try:
            # `joined_on` is stored as dd/mm/YYYY
            return datetime.strptime(self.joined_on, "%d/%m/%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            return parse_dt(self.joined_on)

    @property
    def tenure(self) -> Optional[timedelta]:
        joined = self.joined
        return _now() - joined if joined else None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Staff:
        return cls(
            id=row["staff_id"],
            guild_id=row["guild_id"],
            name=row["name"],
            joined_on=row["joined_on"],
            on_loa=bool(row["on_loa"]),
            retired=bool(row["retired"]),
            stale=bool(row["stale"]),
            responsibility=row["responsibility"],
            avatar_url=row["avatar_url"],
        )

@dataclass(frozen=True, slots=True)
class Leave:
    id: int
    guild_id: int
    staff_id: int
    issued_by: Optional[int] = None
    reason: Optional[str] = None
    days: Optional[int] = None
    started_on: Optional[str] = None
    ended_on: Optional[str] = None

    @property
    def started(self) -> Optional[datetime]:
        return parse_dt(self.started_on)

    @property
    def end(self) -> Optional[datetime]:
        """Actual end if recorded, otherwise start + days."""
        ended = parse_dt(self.ended_on)
        if ended:
            return ended
        started = self.started
        if started and self.days is not None:
            return started + timedelta(days=self.days)
        return None

    def is_ongoing(self, now: Optional[datetime] = None) -> bool:
        now = now or _now()
        started, end = self.started, self.end
        if started is None or started > now:
            return False
        return end is None or now < end

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Leave:
        return cls(
            id=row["leave_id"],
            guild_id=row["guild_id"],
            staff_id=row["staff_id"],
            issued_by=row["issued_by"],
            reason=row["reason"],
            days=row["days"],
            started_on=row["started_on"],
            ended_on=row["ended_on"],
        )

@dataclass(frozen=True, slots=True)
class Strike:
    id: int
    guild_id: int
    issued_by_id: int
    issued_to_id: int
    reason: Optional[str] = None
    date: Optional[str] = None
    expiry_date: Optional[str] = None
    type: Optional[str] = None

    @property
    def issued_at(self) -> Optional[datetime]:
        return parse_dt(self.date)

    @property
    def expires_at(self) -> Optional[datetime]:
        return parse_dt(self.expiry_date)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        expires = self.expires_at
        return expires is not None and expires <= (now or _now())

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Strike:
        return cls(
            id=row["strike_id"],
            guild_id=row["guild_id"],
            issued_by_id=row["issued_by_id"],
            issued_to_id=row["issued_to_id"],
            reason=row["reason"],
            date=row["date"],
            expiry_date=row["expiry_date"],
            type=row["type"],
        )

@dataclass(frozen=True, slots=True)
class StaffQuota:
    id: int
    guild_id: int
    role_id: int
    min_msg: Optional[int] = None
    min_ms: Optional[int] = None
    on_quota_passed: Optional[str] = None
    on_quota_failed: Optional[str] = None
    check_by: Optional[str] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> StaffQuota:
        return cls(
            id=row["quota_id"],
            guild_id=row["guild_id"],
            role_id=row["role_id"],
            min_msg=row["min_msg"],
            min_ms=row["min_ms"],
            on_quota_passed=row["on_quota_passed"],
            on_quota_failed=row["on_quota_failed"],
            check_by=row["check_by"],
        )

@dataclass(frozen=True, slots=True)
class StaffQuotaHistory:
    id: int
    quota_id: int
    staff_id: int
    guild_id: int
    status: Literal["pass", "fail"]
    timestamp: str

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    @property
    def recorded_at(self) -> Optional[datetime]:
        return parse_dt(self.timestamp)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> StaffQuotaHistory:
        return cls(
            id=row["id"],
            quota_id=row["quota_id"],
            staff_id=row["staff_id"],
            guild_id=row["guild_id"],
            status=row["status"],
            timestamp=row["timestamp"],
        )

@dataclass(frozen=True, slots=True)
class RankUpdate:
    id: int
    guild_id: int
    staff_id: int
    updated_by: int
    update_type: Literal["promotion", "demotion"]
    old_role_id: Optional[int] = None
    new_role_id: Optional[int] = None
    reason: Optional[str] = None
    timestamp: Optional[str] = None

    @property
    def is_promotion(self) -> bool:
        return self.update_type == "promotion"

    @property
    def is_demotion(self) -> bool:
        return self.update_type == "demotion"

    @property
    def occurred_at(self) -> Optional[datetime]:
        return parse_dt(self.timestamp)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> RankUpdate:
        return cls(
            id=row["id"],
            guild_id=row["guild_id"],
            staff_id=row["staff_id"],
            updated_by=row["updated_by"],
            update_type=row["update_type"],
            old_role_id=row["old_role_id"],
            new_role_id=row["new_role_id"],
            reason=row["reason"],
            timestamp=row["timestamp"],
        )

@dataclass(frozen=True, slots=True)
class ModLog:
    id: int
    guild_id: int
    moderator_id: int
    target_user_id: int
    mod_type: Optional[str] = None
    reason: Optional[str] = None
    timestamp: Optional[str] = None
    deleted: bool = False
    metadata: dict[str, Any] = field(default_factory=dict, hash=False)

    @property
    def created_at(self) -> Optional[datetime]:
        return parse_dt(self.timestamp)

    @property
    def is_active(self) -> bool:
        return not self.deleted

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ModLog:
        raw = row["metadata"]
        return cls(
            id=row["id"],
            guild_id=row["guild_id"],
            moderator_id=row["moderator_id"],
            target_user_id=row["target_user_id"],
            mod_type=row["mod_type"],
            reason=row["reason"],
            timestamp=row["timestamp"],
            deleted=bool(row["deleted"]),
            metadata=json.loads(raw) if raw else {},
        )

@dataclass(frozen=True, slots=True)
class Ticket:
    id: int
    guild_id: int
    opened_user_id: int
    claimer_user_id: Optional[int] = None
    submission: dict[str, Any] = field(default_factory=dict, hash=False)
    ticket_type: Optional[str] = None
    log_channel_id: Optional[int] = None
    message_id: Optional[int] = None
    ticket_details_message_id: Optional[int] = None

    @property
    def is_claimed(self) -> bool:
        return self.claimer_user_id is not None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Ticket:
        raw = row["submission_json"]
        return cls(
            id=row["ticket_id"],
            guild_id=row["guild_id"],
            opened_user_id=row["opened_user_id"],
            claimer_user_id=row["claimer_user_id"],
            submission=json.loads(raw) if raw else {},
            ticket_type=row["ticket_type"],
            log_channel_id=row["log_channel_id"],
            message_id=row["message_id"],
            ticket_details_message_id=row["ticket_details_message_id"],
        )

@dataclass(frozen=True, slots=True)
class TicketLog:
    id: int
    guild_id: int
    opened_user_id: int
    staff_handled: Optional[int] = None
    reason: Optional[str] = None
    ticket_type: Optional[str] = None
    timestamp: Optional[str] = None
    transcripts_reference: Optional[int] = None
    logs_channel_id: Optional[int] = None

    @property
    def is_handled(self) -> bool:
        return self.staff_handled is not None

    @property
    def opened_at(self) -> Optional[datetime]:
        return parse_dt(self.timestamp)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TicketLog:
        return cls(
            id=row["id"],
            guild_id=row["guild_id"],
            opened_user_id=row["opened_user_id"],
            staff_handled=row["staff_handled"],
            reason=row["reason"],
            ticket_type=row["ticket_type"],
            timestamp=row["timestamp"],
            transcripts_reference=row["transcripts_reference"],
            logs_channel_id=row["logs_channel_id"],
        )



@dataclass(frozen=True, slots=True)
class Appeal:
    case_id: int
    status: str
    thread_id: Optional[int]
    case: ModLog

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Appeal:
        return cls(
            case_id=row["case_id"],
            status=row["status"],
            thread_id=row["thread_id"],
            case=ModLog.from_row(row),
        )

@dataclass(frozen=True, slots=True)
class Tag:
    name: str
    content: str
    created_by: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Tag:
        return cls(name=row["name"], content=row["content"], created_by=row["created_by"])

@dataclass(frozen=True, slots=True)
class PendingLeave:
    id: int
    staff_id: int
    guild_id: int
    message_id: int
    reason: Optional[str] = None
    days: Optional[str] = None
    avatar_url: Optional[str] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> PendingLeave:
        return cls(
            id=row["id"],
            staff_id=row["staff_id"],
            guild_id=row["guild_id"],
            message_id=row["message_id"],
            reason=row["reason"],
            days=row["days"],
            avatar_url=row["avatar_url"],
        )

@dataclass(frozen=True, slots=True)
class StaffCounts:
    total: int = 0
    loa: int = 0
    active: int = 0

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> StaffCounts:
        return cls(
            total=row["total_staffs"],
            loa=row["loa_staffs"],
            active=row["active_staffs"],
        )

@dataclass(frozen=True, slots=True)
class StaffProfile:
    staff: Staff
    timezone: Optional[str] = None
    role_ids: list[int] = field(default_factory=list, hash=False)
    strikes_count: int = 0

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> StaffProfile:
        keys = row.keys()
        raw_roles = row["role_ids"] if "role_ids" in keys else None
        return cls(
            staff=Staff.from_row(row),
            timezone=row["timezone"],
            role_ids=[int(r) for r in raw_roles.split(",")] if raw_roles else [],
            strikes_count=row["strikes_count"] if "strikes_count" in keys else 0,
        )

@dataclass(frozen=True, slots=True)
class RoleStaffGroup:
    role_id: int
    role_type: str
    priority: int
    staff: list[StaffProfile] = field(default_factory=list, hash=False)

@dataclass(frozen=True, slots=True)
class StaffOverview:
    counts: dict[str, StaffCounts]
    roles: list[RoleStaffGroup]

@dataclass(frozen=True, slots=True)
class StaffRoleChanges:
    staff: Staff
    roles_to_add: list[int] = field(default_factory=list, hash=False)
    roles_to_remove: list[int] = field(default_factory=list, hash=False)
    leave: Optional[Leave] = None

@dataclass(frozen=True, slots=True)
class PeriodCounts:
    today: int = 0
    week: int = 0
    month: int = 0
    total: int = 0

@dataclass(frozen=True, slots=True)
class ModStats:
    logs: list[ModLog]
    total_logs: int
    by_type: dict[str, PeriodCounts]
    now: datetime

    def count(self, period: Literal["1d", "7d", "30d", "total"] = "total") -> int:
        attr = {"1d": "today", "7d": "week", "30d": "month", "total": "total"}[period]
        return sum(getattr(c, attr) for c in self.by_type.values())

@dataclass(frozen=True, slots=True)
class QuotaResult:
    quota: StaffQuota
    staff: Staff
    period: Literal["1d", "7d", "30d"]
    messages: int
    mod_stats: int

    @property
    def messages_passed(self) -> bool:
        return self.messages >= (self.quota.min_msg or 0)

    @property
    def mod_stats_passed(self) -> bool:
        return self.mod_stats >= (self.quota.min_ms or 0)

    @property
    def passed(self) -> bool:
        return self.messages_passed and self.mod_stats_passed

    @property
    def failed_reasons(self) -> list[str]:
        return (
            (["messages"] if not self.messages_passed else [])
            + (["moderation stats"] if not self.mod_stats_passed else [])
        )

@dataclass(frozen=True, slots=True)
class MessageCount:
    daily: int = 0
    weekly: int = 0
    monthly: int = 0
    total: int = 0
    xp: int = 0

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> MessageCount:
        return cls(
            daily=row["daily_messages"],
            weekly=row["weekly_messages"],
            monthly=row["monthly_messages"],
            total=row["total_messages"],
            xp=row["total_xp"],
        )

@dataclass(frozen=True, slots=True)
class LevelUp:
    old_level: int
    new_level: int
    progress: dict[str, Any]

@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    rank: int
    member_id: int
    count: int
    name: Optional[str] = None
    avatar_url: Optional[str] = None

@dataclass(frozen=True, slots=True)
class Leaderboard:
    type: str
    page: Page[LeaderboardEntry]
    target: Optional[LeaderboardEntry] = None

@dataclass(frozen=True, slots=True)
class TicketPanel:
    title: Optional[str] = None
    description: Optional[str] = None
    footer_text: Optional[str] = None
    thumbnail_url: Optional[str] = None

@dataclass(frozen=True, slots=True)
class TicketType:
    id: int
    label: str
    ticket_base_name: str
    description: Optional[str] = None
    emoji: Optional[str] = None
    channel_id: Optional[int] = None
    channel_emoji: Optional[str] = None
    fields: list[dict[str, Any]] = field(default_factory=list, hash=False)
    ping_roles: list[int] = field(default_factory=list, hash=False)

    @classmethod
    def from_row(cls, row: sqlite3.Row, ping_roles: list[int]) -> TicketType:
        return cls(
            id=row["id"],
            label=row["label"],
            ticket_base_name=row["ticket_base_name"],
            description=row["description"],
            emoji=row["emoji"],
            channel_id=row["channel_id"],
            channel_emoji=row["channel_emoji"],
            fields=json.loads(row["fields_json"] or "[]"),
            ping_roles=ping_roles,
        )

@dataclass(frozen=True, slots=True)
class TicketView:
    id: int
    guild_id: int
    channel_id: int
    message_id: int
    spawn_channel_id: Optional[int] = None
    logging_channel_id: Optional[int] = None
    ticket_type: Optional[str] = None
    panel: Optional[TicketPanel] = None
    staff_role_ids: list[int] = field(default_factory=list, hash=False)
    types: list[TicketType] = field(default_factory=list, hash=False)

    def get_type(self, base_name: str) -> Optional[TicketType]:
        return next((t for t in self.types if t.ticket_base_name == base_name), None)