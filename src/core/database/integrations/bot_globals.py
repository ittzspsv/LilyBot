from __future__ import annotations


from ..access import LilyDatabaseAccess
from .applications import ApplicationManagement
from .leveling import LevelingManagement
from ...features.leveling.utils.lily_leveling_utils import *
from .models import *

from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, Collection, Literal, Optional, TypeVar

from rapidfuzz import fuzz, process

import json
import sqlite3


T = TypeVar("T")


class LilyError(Exception):
    ...




def _to_int(value: Any) -> int | None:
    """Discord IDs sometimes arrive as strings in hand-written configs."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class BotGlobalsDatabaseAccess(LilyDatabaseAccess):
    def __init__(self):
        super().__init__()

        self.cache: defaultdict[int, dict[str, Any]] = defaultdict(
            lambda: {
                "channels": {},
                "permissions": {},
                "roles": {},
                "prefix": "",
                "secondary_guild_id": None,
            }
        )
        self.member_cache: dict[int, dict[int, str]] = {}
        self._gconfig: Optional[GlobalConfig] = None
        self._cache_ready = False

        self.app_management_db = ApplicationManagement(self)
        self.leveling_db = LevelingManagement(self)

    async def load_cache(self) -> None:
        """
        Cache layout per guild:
        {
            guild_id: {
                channels:    { channel_type: [channel_id, ...] },
                permissions: { command:      [role_id, ...]    },
                roles:       { role_id:      Role },
                prefix: str,
                secondary_guild_id: int | None,
            }
        }
        """
        self.cache.clear()
        self.member_cache.clear()

        for row in await self.fetch_all(
            "SELECT member_id, guild_id, prefix FROM members WHERE prefix IS NOT NULL"
        ):
            self.member_cache.setdefault(row["member_id"], {})[row["guild_id"]] = row["prefix"]

        for row in await self.fetch_all(
            """
            SELECT d.guild_id, d.prefix, gc.secondary_guild_id
            FROM data d
            LEFT JOIN guild_connections gc ON d.guild_id = gc.primary_guild_id
            """
        ):
            entry = self.cache[row["guild_id"]]
            entry["prefix"] = row["prefix"] or ""
            entry["secondary_guild_id"] = row["secondary_guild_id"]

        for row in await self.fetch_all(
            "SELECT guild_id, channel_type, channel_id FROM guild_channels"
        ):
            if (guild := self.cache.get(row["guild_id"])) is None:
                continue
            guild["channels"].setdefault(row["channel_type"], []).append(row["channel_id"])

        for row in await self.fetch_all("SELECT guild_id, role_id, command FROM permissions"):
            if (guild := self.cache.get(row["guild_id"])) is None:
                continue
            guild["permissions"].setdefault(row["command"], []).append(row["role_id"])

        role_rows = await self.fetch_all(
            """
            SELECT
                r.guild_id, r.role_id, r.role_name, r.ban_limit, r.ban_queue,
                r.assignment_scope, r.role_type, ra.target_role_id
            FROM roles r
            LEFT JOIN role_assignments ra
                ON  ra.guild_id = r.guild_id
                AND ra.role_id  = r.role_id
            """
        )
        targets: defaultdict[tuple[int, int], set[int]] = defaultdict(set)
        for row in role_rows:
            if row["target_role_id"] is not None:
                targets[(row["guild_id"], row["role_id"])].add(row["target_role_id"])

        for row in role_rows:
            if (guild := self.cache.get(row["guild_id"])) is None:
                continue
            guild["roles"][row["role_id"]] = Role.from_row(
                row, targets[(row["guild_id"], row["role_id"])]
            )

        row = await self.fetch_one("SELECT value FROM globals WHERE key = 'Jail'")
        if row and row["value"]:
            self._gconfig = GlobalConfig(jail=int(row["value"]))

        self._cache_ready = True

    @property
    def global_config(self) -> Optional[GlobalConfig]:
        return self._gconfig


    def get_prefix(self, guild_id: int) -> str:
        guild = self.cache.get(guild_id)
        return (guild["prefix"] if guild else "") or "."

    def get_prefix_member(self, member_id: int, guild_id: int) -> str | None:
        return self.member_cache.get(member_id, {}).get(guild_id)

    async def set_prefix_member(
        self, member_id: int, guild_id: int, prefix: str | None
    ) -> None:
        await self.execute(
            """
            INSERT INTO members (member_id, guild_id, prefix)
            VALUES (?, ?, ?)
            ON CONFLICT(member_id, guild_id)
            DO UPDATE SET prefix = excluded.prefix
            """,
            (member_id, guild_id, prefix),
        )

        if prefix is None:
            self.member_cache.get(member_id, {}).pop(guild_id, None)
            if not self.member_cache.get(member_id, True):
                del self.member_cache[member_id]
        else:
            self.member_cache.setdefault(member_id, {})[guild_id] = prefix

    async def set_prefix(self, guild_id: int, prefix: str) -> None:
        self.cache[guild_id]["prefix"] = prefix
        await self.execute(
            """
            INSERT INTO data (guild_id, prefix) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix
            """,
            (guild_id, prefix),
        )

    async def guild_initialize(self, guild_id: int) -> None:
        await self.execute("INSERT OR IGNORE INTO data (guild_id) VALUES (?)", (guild_id,))
        self.cache[guild_id]  

    def get_channels(self, guild_id: int, channel_name: str) -> list[int]:
        guild = self.cache.get(guild_id)
        return guild["channels"].get(channel_name, []) if guild else []

    def get_channel(self, guild_id: int, channel_name: str) -> int | None:
        channels = self.get_channels(guild_id, channel_name)
        return channels[0] if channels else None

    async def set_channel(self, guild_id: int, channel_id: int, channel_type: str) -> None:
        channel_list = self.cache[guild_id]["channels"].setdefault(channel_type, [])
        if channel_id not in channel_list:
            channel_list.append(channel_id)

        await self.execute(
            """
            INSERT OR IGNORE INTO guild_channels (guild_id, channel_type, channel_id)
            VALUES (?, ?, ?)
            """,
            (guild_id, channel_type, channel_id),
        )

    async def remove_channel(
        self,
        guild_id: int,
        channel_id: Optional[int] = None,
        channel_type: Optional[str] = None,
    ) -> None:
        if channel_id is None and channel_type is None:
            raise ValueError("remove_channel requires at least one of channel_id or channel_type")

        if (guild := self.cache.get(guild_id)) is not None:
            channels = guild["channels"]
            for ctype in list(channels):
                if channel_type not in (None, ctype):
                    continue
                channels[ctype] = (
                    [] if channel_id is None else [c for c in channels[ctype] if c != channel_id]
                )
                if not channels[ctype]:
                    del channels[ctype]

        conditions, params = ["guild_id = ?"], [guild_id]
        if channel_id is not None:
            conditions.append("channel_id = ?")
            params.append(channel_id)
        if channel_type is not None:
            conditions.append("channel_type = ?")
            params.append(channel_type)

        await self.execute(
            f"DELETE FROM guild_channels WHERE {' AND '.join(conditions)}", tuple(params)
        )

    async def set_webhook(self, guild_id: int, channel_type: str, webhook_url: str) -> None:
        await self.execute(
            """
            INSERT INTO guild_webhooks (guild_id, channel_type, webhook_url)
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id, channel_type)
            DO UPDATE SET webhook_url = excluded.webhook_url
            """,
            (guild_id, channel_type, webhook_url),
        )

    async def get_webhooks_of_type(self, channel_type: str) -> dict[int, str | None]:
        rows = await self.fetch_all(
            "SELECT guild_id, webhook_url FROM guild_webhooks WHERE channel_type = ?",
            (channel_type,),
        )
        return {row["guild_id"]: row["webhook_url"] for row in rows}

    async def get_webhook(self, guild_id: int, channel_type: str) -> str | None:
        row = await self.fetch_one(
            """
            SELECT webhook_url FROM guild_webhooks
            WHERE guild_id = ? AND channel_type = ?
            LIMIT 1
            """,
            (guild_id, channel_type),
        )
        return row["webhook_url"] if row else None

    def has_permission(self, guild_id: int, command: str | None, roles: list[int]) -> bool:
        if command is None or (guild := self.cache.get(guild_id)) is None:
            return False
        allowed_roles = guild["permissions"].get(command, [])
        return any(role_id in allowed_roles for role_id in roles)

    def get_permissions(self, guild_id: int, role_ids: Collection[int]) -> set[str]:
        """Every command any of ``role_ids`` may use."""
        if (guild := self.cache.get(guild_id)) is None:
            return set()
        ids = set(role_ids)
        return {cmd for cmd, allowed in guild["permissions"].items() if ids.intersection(allowed)}

    def get_permission_roles(self, guild_id: int, command: str | None) -> list[int]:
        if command is None or (guild := self.cache.get(guild_id)) is None:
            return []
        return guild["permissions"].get(command, [])

    async def set_permission(self, guild_id: int, role_id: int, command: str) -> None:
        role_list = self.cache[guild_id]["permissions"].setdefault(command, [])
        if role_id not in role_list:
            role_list.append(role_id)

        await self.execute(
            "INSERT OR IGNORE INTO permissions (guild_id, role_id, command) VALUES (?, ?, ?)",
            (guild_id, role_id, command),
        )

    async def remove_permission(
        self, guild_id: int, role_id: int, command: Optional[str] = None
    ) -> None:
        if (guild := self.cache.get(guild_id)) is not None:
            permissions = guild["permissions"]
            for cmd in list(permissions):
                if command not in (None, cmd):
                    continue
                if role_id in permissions[cmd]:
                    permissions[cmd].remove(role_id)
                if not permissions[cmd]:
                    del permissions[cmd]

        conditions, params = ["guild_id = ?", "role_id = ?"], [guild_id, role_id]
        if command:
            conditions.append("command = ?")
            params.append(command)

        await self.execute(
            f"DELETE FROM permissions WHERE {' AND '.join(conditions)}", tuple(params)
        )

    # ----------------------------------------------------------------------- #
    # Roles
    # ----------------------------------------------------------------------- #

    async def get_role_of_type(self, guild_id: int, role_type: str) -> list[int]:
        rows = await self.fetch_all(
            "SELECT role_id FROM roles WHERE guild_id = ? AND role_type = ?",
            (guild_id, role_type),
        )
        return [row[0] for row in rows]

    async def delete_role_of_type(self, guild_id: int, role_type: str) -> None:
        await self.execute(
            "DELETE FROM roles WHERE guild_id = ? AND role_type = ?", (guild_id, role_type)
        )

    def get_ban_limit(self, guild_id: int, role_ids: list[int]) -> int:
        if (guild := self.cache.get(guild_id)) is None:
            return 0
        return max(
            (role.ban_limit or 0 for rid in role_ids if (role := guild["roles"].get(rid))),
            default=0,
        )

    def ban_queue(self, guild_id: int, role_ids: list[int]) -> bool:
        """True only if every configured role the member has allows the ban queue."""
        if (guild := self.cache.get(guild_id)) is None:
            return False
        roles = [role for rid in role_ids if (role := guild["roles"].get(rid))]
        return bool(roles) and all(role.ban_queue for role in roles)

    def can_assign_role(
        self, guild_id: int, author_role_ids: list[int], target_role_id: int
    ) -> bool:
        if (guild := self.cache.get(guild_id)) is None:
            return False
        roles = [role for rid in author_role_ids if (role := guild["roles"].get(rid))]

        if any(role.role_assignment_scope == "all" for role in roles):
            return True

        specific: set[int] = set()
        excepts: set[int] = set()
        has_except_scope = False
        for role in roles:
            if role.role_assignment_scope == "specific":
                specific |= role.assignment_roles
            elif role.role_assignment_scope == "except":
                has_except_scope = True
                excepts |= role.assignment_roles

        if target_role_id in specific:
            return True
        return has_except_scope and target_role_id not in (excepts - specific)

    async def get_role_configuration(self, guild_id: int, role_id: int) -> Role | None:
        row = await self.fetch_one(
            """
            SELECT guild_id, role_id, role_name, ban_limit, ban_queue, assignment_scope, role_type
            FROM roles
            WHERE guild_id = ? AND role_id = ?
            """,
            (guild_id, role_id),
        )
        if row is None:
            return None

        assignment_rows = await self.fetch_all(
            "SELECT target_role_id FROM role_assignments WHERE guild_id = ? AND role_id = ?",
            (guild_id, role_id),
        )
        return Role.from_row(row, [r["target_role_id"] for r in assignment_rows])

    async def configure_role(
        self,
        guild_id: int,
        role_id: int,
        ban_limit: int = 45,
        ban_queue: int = 0,
        assignment_scope: str = "none",
        roles: Collection[int] = (),
        role_type: str = "staff",
        overwrite: bool = True,
    ) -> Role:
        """Create/update a role config. With ``overwrite=False`` an existing config is kept untouched."""
        role = None if overwrite else await self.get_role_configuration(guild_id, role_id)

        if role is None:
            await self.execute(
                """
                INSERT INTO roles (
                    guild_id, role_id, ban_limit, ban_queue, assignment_scope, role_type
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, role_id) DO UPDATE SET
                    ban_limit        = excluded.ban_limit,
                    ban_queue        = excluded.ban_queue,
                    assignment_scope = excluded.assignment_scope,
                    role_type        = excluded.role_type
                """,
                (guild_id, role_id, ban_limit, ban_queue, assignment_scope, role_type),
            )
            await self.execute(
                "DELETE FROM role_assignments WHERE guild_id = ? AND role_id = ?",
                (guild_id, role_id),
            )
            await self.executemany(
                """
                INSERT OR IGNORE INTO role_assignments (guild_id, role_id, target_role_id)
                VALUES (?, ?, ?)
                """,
                [(guild_id, role_id, target) for target in roles],
            )
            role = await self.get_role_configuration(guild_id, role_id)

        self.cache[guild_id]["roles"][role_id] = role
        return role  # type: ignore[return-value]

    async def remove_role(self, guild_id: int, role_id: int) -> Role:
        role = await self.get_role_configuration(guild_id, role_id)
        if role is None:
            raise LilyError("Role is not configured.")

        await self.execute(
            "DELETE FROM staff_roles WHERE role_id = ? AND guild_id = ?", (role_id, guild_id)
        )
        await self.execute(
            "DELETE FROM staff_quota WHERE role_id = ? AND guild_id = ?", (role_id, guild_id)
        )
        await self.execute(
            "DELETE FROM roles WHERE role_id = ? AND guild_id = ?", (role_id, guild_id)
        )

        if (guild := self.cache.get(guild_id)) is not None:
            guild["roles"].pop(role_id, None)

        return role

    async def rank_setup(self, guild_id: int, role_id: dict[int, int]) -> None:
        """``role_id`` maps role_id -> sort key; highest key becomes priority 0 (top rank)."""
        ranked = sorted(role_id.items(), key=lambda item: item[1], reverse=True)

        await self.execute("DELETE FROM staff_ranks WHERE guild_id = ?", (guild_id,))

        for role, _ in ranked:
            await self.configure_role(guild_id, role, overwrite=False)

        await self.executemany(
            "INSERT INTO staff_ranks (guild_id, role_id, priority) VALUES (?, ?, ?)",
            [(guild_id, role, priority) for priority, (role, _) in enumerate(ranked)],
        )

    async def get_staff_ranks(self, guild_id: int) -> list[int]:
        rows = await self.fetch_all(
            "SELECT role_id FROM staff_ranks WHERE guild_id = ? ORDER BY priority ASC",
            (guild_id,),
        )
        return [row["role_id"] for row in rows]

    # ----------------------------------------------------------------------- #
    # Members / AFK / timezone
    # ----------------------------------------------------------------------- #

    async def ensure_member(self, member_id: int, guild_id: int) -> None:
        await self.execute(
            "INSERT OR IGNORE INTO members (member_id, guild_id) VALUES (?, ?)",
            (member_id, guild_id),
        )

    async def get_member(self, member_id: int, guild_id: int) -> Member:
        guild = GuildObject(id=guild_id, prefix=self.get_prefix(guild_id))
        row = await self.fetch_one(
            """
            SELECT m.member_id, m.name, m.timezone, m.prefix, m.avatar_url,
                   a.timestamp, a.display_name, a.reason
            FROM members m
            LEFT JOIN afk a
                ON a.member_id = m.member_id AND a.guild_id = m.guild_id
            WHERE m.member_id = ? AND m.guild_id = ?
            """,
            (member_id, guild_id),
        )
        if row is None:
            return Member(id=member_id, guild=guild)

        afk = AFK.from_row(row) if row["timestamp"] is not None else None
        return Member.from_row(row, guild, afk)

    async def set_timezone(self, member_id: int, guild_id: int, timezone: str) -> Member:
        await self.execute(
            """
            INSERT INTO members (member_id, guild_id, timezone)
            VALUES (?, ?, ?)
            ON CONFLICT (member_id, guild_id)
            DO UPDATE SET timezone = excluded.timezone
            """,
            (member_id, guild_id, timezone),
        )
        return await self.get_member(member_id, guild_id)

    async def afk_set(
        self, member_id: int, guild_id: int, reason: str, display_name: str
    ) -> AFK:
        await self.ensure_member(member_id, guild_id)
        timestamp = datetime.now(UTC).isoformat()
        await self.execute(
            """
            INSERT INTO afk (member_id, guild_id, timestamp, display_name, reason)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (member_id, guild_id)
            DO UPDATE SET timestamp = excluded.timestamp,
                          display_name = excluded.display_name,
                          reason = excluded.reason
            """,
            (member_id, guild_id, timestamp, display_name, reason),
        )
        return AFK(timestamp=timestamp, display_name=display_name, reason=reason)

    async def afk_clear(self, member_id: int, guild_id: int) -> AFK | None:
        row = await self.fetch_one(
            "SELECT timestamp, display_name, reason FROM afk WHERE member_id = ? AND guild_id = ?",
            (member_id, guild_id),
        )
        if row is None:
            return None

        await self.execute(
            "DELETE FROM afk WHERE member_id = ? AND guild_id = ?", (member_id, guild_id)
        )
        return AFK.from_row(row)

    async def get_afk_entries(self, guild_id: int) -> dict[int, AFK]:
        rows = await self.fetch_all(
            "SELECT member_id, timestamp, display_name, reason FROM afk WHERE guild_id = ?",
            (guild_id,),
        )
        return {row["member_id"]: AFK.from_row(row) for row in rows}

    # ----------------------------------------------------------------------- #
    # Ticket panels
    # ----------------------------------------------------------------------- #

    @staticmethod
    def validate_ticket_config(config: dict) -> None:
        tickets = config.get("Tickets")
        if not isinstance(config.get("BasicConfigurations"), dict) or not isinstance(tickets, list) or not tickets:
            raise LilyError("`BasicConfigurations` and a non-empty `Tickets` list are required.")

        if len(tickets) > 25:
            raise LilyError("A panel can hold at most 25 ticket types.")

        names = [ticket.get("ticket_base_name") for ticket in tickets]
        if not all(names) or not all(ticket.get("label") for ticket in tickets):
            raise LilyError("Every ticket needs a `label` and a `ticket_base_name`.")

        if len(set(names)) != len(names):
            raise LilyError("`ticket_base_name` must be unique within a panel.")

    async def save_ticket_view(
        self, guild_id: int, channel_id: int, message_id: int, config: dict
    ) -> TicketView:
        """Create the panel row if needed and replace its config."""
        self.validate_ticket_config(config)

        basic = config.get("BasicConfigurations") or {}
        panel = config.get("PanelConfig") or {}

        async with self.transaction() as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO ticket_views (guild_id, channel_id, message_id, config_json)
                VALUES (?, ?, ?, '{}')
                """,
                (guild_id, channel_id, message_id),
            )
            row = await conn.fetchone(
                "SELECT id FROM ticket_views WHERE guild_id = ? AND channel_id = ? AND message_id = ?",
                (guild_id, channel_id, message_id),
            )
            view_id: int = row["id"]

            for table in (
                "ticket_view_settings",
                "ticket_view_panel",
                "ticket_view_staff_roles",
                "ticket_view_types",
            ):
                await conn.execute(f"DELETE FROM {table} WHERE view_id = ?", (view_id,))

            await conn.execute(
                """
                INSERT INTO ticket_view_settings
                    (view_id, spawn_channel_id, logging_channel_id, ticket_type)
                VALUES (?, ?, ?, ?)
                """,
                (
                    view_id,
                    _to_int(basic.get("TicketPanelSpawnChannel")),
                    _to_int(basic.get("TicketLoggingHandler")),
                    basic.get("TicketType"),
                ),
            )

            if panel:
                await conn.execute(
                    """
                    INSERT INTO ticket_view_panel
                        (view_id, title, description, footer_text, thumbnail_url)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        view_id,
                        panel.get("title"),
                        panel.get("description"),
                        (panel.get("footer") or {}).get("text"),
                        (panel.get("thumbnail") or {}).get("url"),
                    ),
                )

            staff_roles = {_to_int(r) for r in basic.get("higher_staffs_role_id") or []} - {None}
            if staff_roles:
                await conn.executemany(
                    "INSERT INTO ticket_view_staff_roles (view_id, role_id) VALUES (?, ?)",
                    [(view_id, role_id) for role_id in staff_roles],
                )

            for position, ticket in enumerate(config["Tickets"]):
                cursor = await conn.execute(
                    """
                    INSERT INTO ticket_view_types (
                        view_id, position, label, description, emoji,
                        channel_id, channel_emoji, ticket_base_name, fields_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        view_id,
                        position,
                        ticket["label"],
                        ticket.get("description"),
                        ticket.get("emoji"),
                        _to_int(ticket.get("channel_id")),
                        ticket.get("channel_emoji"),
                        ticket["ticket_base_name"],
                        json.dumps(ticket.get("fields") or []),
                    ),
                )
                type_id = cursor.get_cursor().lastrowid

                ping_roles = {_to_int(r) for r in ticket.get("ping_roles") or []} - {None}
                if ping_roles:
                    await conn.executemany(
                        "INSERT INTO ticket_view_type_ping_roles (type_id, role_id) VALUES (?, ?)",
                        [(type_id, role_id) for role_id in ping_roles],
                    )

        view = await self.get_ticket_view(view_id=view_id)
        assert view is not None
        return view

    async def get_ticket_view(
        self,
        *,
        view_id: int | None = None,
        message_id: int | None = None,
        guild_id: int | None = None,
    ) -> TicketView | None:
        """Load one panel completely (settings, embed, staff roles, ticket types + ping roles)."""
        conditions, params = [], []
        if view_id is not None:
            conditions.append("v.id = ?")
            params.append(view_id)
        if message_id is not None:
            conditions.append("v.message_id = ?")
            params.append(message_id)
        if guild_id is not None:
            conditions.append("v.guild_id = ?")
            params.append(guild_id)
        if view_id is None and message_id is None:
            raise ValueError("get_ticket_view needs view_id or message_id")

        row = await self.fetch_one(
            f"""
            SELECT v.id, v.guild_id, v.channel_id, v.message_id,
                   s.spawn_channel_id, s.logging_channel_id, s.ticket_type,
                   p.view_id IS NOT NULL AS has_panel,
                   p.title, p.description, p.footer_text, p.thumbnail_url
            FROM ticket_views v
            LEFT JOIN ticket_view_settings s ON s.view_id = v.id
            LEFT JOIN ticket_view_panel p ON p.view_id = v.id
            WHERE {' AND '.join(conditions)}
            """,
            tuple(params),
        )
        if row is None:
            return None

        staff_rows = await self.fetch_all(
            "SELECT role_id FROM ticket_view_staff_roles WHERE view_id = ?", (row["id"],)
        )
        type_rows = await self.fetch_all(
            """
            SELECT id, label, description, emoji, channel_id, channel_emoji,
                   ticket_base_name, fields_json
            FROM ticket_view_types
            WHERE view_id = ?
            ORDER BY position
            """,
            (row["id"],),
        )
        ping_rows = await self.fetch_all(
            """
            SELECT r.type_id, r.role_id
            FROM ticket_view_type_ping_roles r
            JOIN ticket_view_types t ON t.id = r.type_id
            WHERE t.view_id = ?
            """,
            (row["id"],),
        )
        pings: defaultdict[int, list[int]] = defaultdict(list)
        for ping in ping_rows:
            pings[ping["type_id"]].append(ping["role_id"])

        return TicketView(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            spawn_channel_id=row["spawn_channel_id"],
            logging_channel_id=row["logging_channel_id"],
            ticket_type=row["ticket_type"],
            panel=(
                TicketPanel(
                    title=row["title"],
                    description=row["description"],
                    footer_text=row["footer_text"],
                    thumbnail_url=row["thumbnail_url"],
                )
                if row["has_panel"]
                else None
            ),
            staff_role_ids=[r["role_id"] for r in staff_rows],
            types=[TicketType.from_row(r, pings[r["id"]]) for r in type_rows],
        )

    async def get_ticket_views(self, guild_id: int | None = None) -> list[TicketView]:
        query = "SELECT id FROM ticket_views"
        params: tuple = ()
        if guild_id is not None:
            query += " WHERE guild_id = ?"
            params = (guild_id,)

        rows = await self.fetch_all(query + " ORDER BY id", params)
        views = [await self.get_ticket_view(view_id=row["id"]) for row in rows]
        return [view for view in views if view is not None]

    async def delete_ticket_view(self, message_id: int) -> TicketView:
        view = await self.get_ticket_view(message_id=message_id)
        if view is None:
            raise LilyError("Ticket panel not found.")
        await self.execute("DELETE FROM ticket_views WHERE message_id = ?", (message_id,))
        return view

    # ----------------------------------------------------------------------- #
    # Bot logs
    # ----------------------------------------------------------------------- #

    async def write_log(self, guild_id: int, user_id: int, log_txt: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.execute(
            "INSERT INTO botlogs (guild_id, member_id, timestamp, log) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, timestamp, log_txt),
        )

    # ----------------------------------------------------------------------- #
    # Moderation
    # ----------------------------------------------------------------------- #

    async def log_moderation_action(
        self,
        guild_id: int,
        moderator_id: int,
        target_user_id: int,
        mod_type: str,
        reason: str = "No reason provided",
        metadata: Optional[dict[str, Any]] = None,
    ) -> ModLog:
        metadata = metadata or {}
        mod_type = mod_type.lower()
        timestamp = datetime.now(UTC).isoformat()

        await self.ensure_staff(moderator_id, guild_id)
        await self.ensure_member(target_user_id, guild_id)

        case_id = await self.execute(
            """
            INSERT INTO modlogs
                (guild_id, moderator_id, target_user_id, mod_type, reason, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, moderator_id, target_user_id, mod_type, reason, timestamp, json.dumps(metadata)),
        )

        return ModLog(
            id=case_id,  # type: ignore[arg-type]
            guild_id=guild_id,
            moderator_id=moderator_id,
            target_user_id=target_user_id,
            mod_type=mod_type,
            reason=reason,
            timestamp=timestamp,
            metadata=metadata,
        )

    async def log_proof_action(
        self, guild_id: int, case_id: int, proof_reference: int, author: int
    ) -> None:
        await self.ensure_staff(author, guild_id)
        await self.execute(
            """
            INSERT INTO proofs (guild_id, case_id, proof_reference, author)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, case_id, proof_reference, author),
        )

    async def get_proof_references(self, case_id: int, guild_id: int | None = None) -> list[int]:
        query = "SELECT proof_reference FROM proofs WHERE case_id = ?"
        params: tuple = (case_id,)
        if guild_id is not None:
            query += " AND guild_id = ?"
            params += (guild_id,)

        rows = await self.fetch_all(query + " ORDER BY id ASC", params)
        return [row["proof_reference"] for row in rows]

    async def get_ban_limit_status(
        self, guild_id: int, moderator_id: int, moderator_role_ids: list[int]
    ) -> BanLimitStatus:
        _default = BanLimitStatus(
            exceeded=True,
            max_limit=0,
            recent_ban_count=0,
            remaining_count=0,
            remaining_time=None,
            cooldown_breakdown=None,
        )
        if not moderator_role_ids:
            return _default

        now = datetime.now(UTC)

        try:
            max_limit = self.get_ban_limit(guild_id, moderator_role_ids)
            if max_limit == 0:
                return _default

            bans = await self.fetch_all(
                """
                SELECT timestamp
                FROM modlogs
                WHERE guild_id = ?
                AND deleted = 0
                AND moderator_id = ?
                AND mod_type IN ('ban', 'quarantine')
                AND timestamp >= ?
                ORDER BY timestamp ASC
                """,
                (guild_id, moderator_id, (now - timedelta(hours=24)).isoformat()),
            )

            recent_ban_count = len(bans)
            exceeded = recent_ban_count >= max_limit
            remaining_time: Optional[str] = None
            cooldown_breakdown: Optional[str] = None

            if exceeded:
                lines = []
                for index, row in enumerate(bans, start=1):
                    remaining = parse_dt(row["timestamp"]) + timedelta(hours=24) - now  # type: ignore[operator]
                    if remaining.total_seconds() <= 0:
                        continue
                    hours, minutes = divmod(int(remaining.total_seconds()) // 60, 60)
                    lines.append(f"{index}. Recovery in **{hours}h {minutes}m**")
                    if remaining_time is None:
                        remaining_time = f"You can ban again in {hours}h {minutes}m"

                if lines:
                    cooldown_breakdown = "**Ban's Cooldown State.**\n" + "\n".join(lines)

            return BanLimitStatus(
                exceeded=exceeded,
                max_limit=max_limit,
                recent_ban_count=recent_ban_count,
                remaining_count=max(0, max_limit - recent_ban_count),
                remaining_time=remaining_time,
                cooldown_breakdown=cooldown_breakdown,
            )

        except Exception as exc:
            print("Error in get_ban_limit_status:", exc)
            return _default

    async def fetch_mod_stats(
        self, guild_id: int, moderator_id: int, page_start: int = 0, page_end: int = 0
    ) -> ModStats:
        """Per-type counters + logs[page_start:page_end] (no logs are fetched when the range is empty)."""
        now = datetime.now(UTC)
        start_today = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        start_week = (
            (now - timedelta(days=(now.weekday() + 1) % 7))
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .isoformat()
        )
        start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

        stats_rows = await self.fetch_all(
            """
            SELECT
                mod_type,
                COUNT(*) AS total,
                COUNT(CASE WHEN timestamp >= ? THEN 1 END) AS today,
                COUNT(CASE WHEN timestamp >= ? THEN 1 END) AS week,
                COUNT(CASE WHEN timestamp >= ? THEN 1 END) AS month
            FROM modlogs
            WHERE guild_id = ?
              AND moderator_id = ?
              AND deleted = 0
              AND LOWER(mod_type) NOT IN ('unban', 'unmute', 'quarantine_release')
            GROUP BY mod_type
            """,
            (start_today, start_week, start_month, guild_id, moderator_id),
        )

        logs: list[ModLog] = []
        if stats_rows and page_end > page_start:
            page_rows = await self.fetch_all(
                """
                SELECT id, guild_id, moderator_id, target_user_id, mod_type,
                       reason, timestamp, deleted, metadata
                FROM modlogs
                WHERE guild_id = ?
                  AND moderator_id = ?
                  AND deleted = 0
                  AND LOWER(mod_type) NOT IN ('unban', 'unmute', 'quarantine_release')
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (guild_id, moderator_id, page_end - page_start, page_start),
            )
            logs = [ModLog.from_row(row) for row in page_rows]

        return ModStats(
            logs=logs,
            total_logs=sum(row["total"] for row in stats_rows),
            by_type={
                row["mod_type"].lower(): PeriodCounts(
                    today=row["today"], week=row["week"], month=row["month"], total=row["total"]
                )
                for row in stats_rows
            },
            now=now,
        )

    async def fetch_mod_logs(
        self,
        guild_id: int,
        target_user_id: int,
        *,
        moderator_id: int | None = None,
        mod_type: str = "all",
        page: int = 1,
        page_size: int = 3,
    ) -> Page[ModLog]:
        """If there is a secondary guild id then we fetch modlogs of that guild instead."""

        conditions = ["guild_id = ?", "target_user_id = ?", "deleted = 0"]
        params: list[Any] = [guild_id, target_user_id]

        if moderator_id is not None:
            conditions.append("moderator_id = ?")
            params.append(moderator_id)

        if mod_type.lower() != "all":
            conditions.append("lower(mod_type) = ?")
            params.append(mod_type.lower())

        where_clause = " AND ".join(conditions)

        count_row = await self.fetch_one(
            f"SELECT COUNT(*) AS total FROM modlogs WHERE {where_clause}", tuple(params)
        )
        rows = await self.fetch_all(
            f"""
            SELECT id, guild_id, moderator_id, target_user_id, mod_type,
                   reason, timestamp, deleted, metadata
            FROM modlogs
            WHERE {where_clause}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params) + (page_size, (page - 1) * page_size),
        )

        return Page(
            items=[ModLog.from_row(row) for row in rows],
            page=page,
            page_size=page_size,
            total_count=count_row["total"] if count_row else 0,
        )

    async def fetch_moderation_leaderboard(
        self, guild_id: int, lb_type: str = "total"
    ) -> list[LeaderboardEntry]:
        lb_type = lb_type if lb_type in {"total", "daily", "weekly", "monthly"} else "total"

        rows = await self.fetch_all(
            f"""
            SELECT
                m.moderator_id,
                COUNT(*) AS total,
                COUNT(CASE
                    WHEN datetime(replace(substr(m.timestamp,1,19),'T',' '))
                        >= datetime('now','start of day')
                    THEN 1 END) AS daily,
                COUNT(CASE
                    WHEN datetime(replace(substr(m.timestamp,1,19),'T',' '))
                        >= datetime('now','weekday 0','start of day','-7 days')
                    THEN 1 END) AS weekly,
                COUNT(CASE
                    WHEN datetime(replace(substr(m.timestamp,1,19),'T',' '))
                        >= datetime('now','start of month')
                    THEN 1 END) AS monthly
            FROM modlogs m
            JOIN staffs s
                ON s.staff_id = m.moderator_id
               AND s.guild_id = m.guild_id
            WHERE m.guild_id = ?
              AND m.deleted = 0
              AND s.on_loa = 0
              AND s.retired = 0
              AND LOWER(m.mod_type) NOT IN ('unban', 'unmute', 'quarantine_release')
            GROUP BY m.moderator_id
            ORDER BY {lb_type} DESC
            """,
            (guild_id,),
        )

        return [
            LeaderboardEntry(rank=rank, member_id=row["moderator_id"], count=row[lb_type])
            for rank, row in enumerate(rows, start=1)
        ]

    async def get_case(self, case_id: int, guild_id: int | None = None) -> ModLog | None:
        """Returns the case even if it is soft-deleted; check ``.deleted``."""
        query = """
            SELECT id, guild_id, moderator_id, target_user_id, mod_type,
                   reason, timestamp, deleted, metadata
            FROM modlogs
            WHERE id = ?
        """
        params: tuple = (case_id,)
        if guild_id is not None:
            query += " AND guild_id = ?"
            params += (guild_id,)

        row = await self.fetch_one(query, params)
        return ModLog.from_row(row) if row else None

    async def get_case_latest(
        self, case_type: str, guild_id: int, target_user_id: Optional[int] = None
    ) -> ModLog | None:
        conditions = ["guild_id = ?", "mod_type = ?", "deleted = 0"]
        params: list[Any] = [guild_id, case_type]

        if target_user_id is not None:
            conditions.append("target_user_id = ?")
            params.append(target_user_id)

        row = await self.fetch_one(
            f"""
            SELECT id, guild_id, moderator_id, target_user_id, mod_type,
                   reason, timestamp, deleted, metadata
            FROM modlogs
            WHERE {' AND '.join(conditions)}
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            tuple(params),
        )
        return ModLog.from_row(row) if row else None

    async def get_active_quarantine(self, member_id: int, guild_id: int) -> ModLog | None:
        """The member's open quarantine case (not released, not deleted), if any."""
        row = await self.fetch_one(
            """
            SELECT q.id, q.guild_id, q.moderator_id, q.target_user_id, q.mod_type,
                   q.reason, q.timestamp, q.deleted, q.metadata
            FROM modlogs q
            WHERE q.guild_id = ?
              AND q.target_user_id = ?
              AND q.mod_type = 'quarantine'
              AND q.deleted = 0
              AND NOT EXISTS (
                  SELECT 1
                  FROM modlogs r
                  WHERE r.guild_id = q.guild_id
                    AND r.target_user_id = q.target_user_id
                    AND r.mod_type = 'quarantine_release'
                    AND r.id > q.id
                    AND r.deleted = 0
              )
            ORDER BY q.id DESC
            LIMIT 1
            """,
            (guild_id, member_id),
        )
        return ModLog.from_row(row) if row else None

    async def edit_case(
        self, staff_id: int, case_id: int, case_statement: str, absolute: bool
    ) -> Edit[ModLog]:
        before = await self.get_case(case_id)
        if before is None or before.deleted:
            raise LilyError("Case not found.")

        if before.moderator_id != staff_id and not absolute:
            raise LilyError(
                f"This case cannot be modified. Only <@{before.moderator_id}> can modify it."
            )

        await self.execute("UPDATE modlogs SET reason = ? WHERE id = ?", (case_statement, case_id))
        return Edit(before=before, after=replace(before, reason=case_statement))

    async def delete_case(self, case_id: int, guild_id: int) -> ModLog:
        case = await self.get_case(case_id, guild_id)
        if case is None or case.deleted:
            raise LilyError("Case not found.")

        await self.execute(
            "UPDATE modlogs SET deleted = 1 WHERE id = ? AND guild_id = ?", (case_id, guild_id)
        )
        return replace(case, deleted=True)

    # ----------------------------------------------------------------------- #
    # Appeals
    # ----------------------------------------------------------------------- #

    async def upsert_appeal_forum(self, guild_id: int, config: str) -> None:
        await self.execute(
            """
            INSERT INTO mod_appeal_forum (guild_id, config)
            VALUES (?, ?)
            ON CONFLICT(guild_id)
            DO UPDATE SET config = excluded.config
            """,
            (guild_id, config),
        )

    async def get_appeal_forum_config(self, guild_id: int) -> list[dict[str, str]]:
        row = await self.fetch_one(
            "SELECT config FROM mod_appeal_forum WHERE guild_id = ?", (guild_id,)
        )
        return json.loads(row["config"]) if row else []

    async def get_appeal(
        self,
        *,
        case_id: int | None = None,
        thread_id: int | None = None,
        member_id: int | None = None,
        pending_only: bool = False,
    ) -> Appeal | None:
        """Latest appeal matching the filters (``member_id`` = the punished user)."""
        conditions, params = [], []
        if case_id is not None:
            conditions.append("ma.case_id = ?")
            params.append(case_id)
        if thread_id is not None:
            conditions.append("ma.thread_id = ?")
            params.append(thread_id)
        if member_id is not None:
            conditions.append("m.target_user_id = ?")
            params.append(member_id)
        if not conditions:
            raise ValueError("get_appeal needs case_id, thread_id or member_id")
        if pending_only:
            conditions.append("ma.status = 'pending'")

        row = await self.fetch_one(
            f"""
            SELECT ma.case_id, ma.status, ma.thread_id,
                   m.id, m.guild_id, m.moderator_id, m.target_user_id, m.mod_type,
                   m.reason, m.timestamp, m.deleted, m.metadata
            FROM mod_appeal ma
            JOIN modlogs m ON m.id = ma.case_id
            WHERE {' AND '.join(conditions)}
            ORDER BY m.id DESC
            LIMIT 1
            """,
            tuple(params),
        )
        return Appeal.from_row(row) if row else None

    async def create_appeal(self, case_id: int, thread_id: int) -> Appeal:
        await self.execute(
            "INSERT INTO mod_appeal (case_id, status, thread_id) VALUES (?, 'pending', ?)",
            (case_id, thread_id),
        )
        appeal = await self.get_appeal(case_id=case_id)
        assert appeal is not None
        return appeal

    async def set_appeal_status(self, case_id: int, status: str) -> Appeal:
        updated = await self.execute(
            "UPDATE mod_appeal SET status = ? WHERE case_id = ?",
            (status, case_id),
            row_count=True,
        )
        appeal = await self.get_appeal(case_id=case_id) if updated else None
        if appeal is None:
            raise LilyError("Appeal not found.")
        return appeal

    # ----------------------------------------------------------------------- #
    # Tickets
    # ----------------------------------------------------------------------- #

    async def get_ticket_by_id(self, ticket_id: int) -> Ticket | None:
        row = await self.fetch_one(
            """
            SELECT ticket_id, guild_id, opened_user_id, claimer_user_id, submission_json,
                   ticket_type, log_channel_id, message_id, ticket_details_message_id
            FROM tickets
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        )
        return Ticket.from_row(row) if row else None

    async def get_ticket_by_opener(self, opener_id: int, guild_id: int) -> list[Ticket]:
        rows = await self.fetch_all(
            """
            SELECT ticket_id, guild_id, opened_user_id, claimer_user_id, submission_json,
                   ticket_type, log_channel_id, message_id, ticket_details_message_id
            FROM tickets
            WHERE opened_user_id = ? AND guild_id = ?
            """,
            (opener_id, guild_id),
        )
        return [Ticket.from_row(row) for row in rows]

    async def get_guild_tickets(self, guild_id: int) -> list[Ticket]:
        rows = await self.fetch_all(
            """
            SELECT ticket_id, guild_id, opened_user_id, claimer_user_id, submission_json,
                   ticket_type, log_channel_id, message_id, ticket_details_message_id
            FROM tickets
            WHERE guild_id = ?
            """,
            (guild_id,),
        )
        return [Ticket.from_row(row) for row in rows]

    async def create_ticket(
        self,
        ticket_id: int,
        guild_id: int,
        opened_user_id: int,
        ticket_type: str,
        log_channel_id: int,
        submission_json: dict,
        message_id: Optional[int] = None,
        ticket_details_message_id: Optional[int] = None,
    ) -> Ticket:
        await self.ensure_member(opened_user_id, guild_id)
        await self.execute(
            """
            INSERT INTO tickets (
                ticket_id, guild_id, opened_user_id, ticket_type,
                log_channel_id, submission_json, message_id, ticket_details_message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id, guild_id, opened_user_id, ticket_type, log_channel_id,
                json.dumps(submission_json), message_id, ticket_details_message_id,
            ),
        )
        return Ticket(
            id=ticket_id,
            guild_id=guild_id,
            opened_user_id=opened_user_id,
            submission=submission_json,
            ticket_type=ticket_type,
            log_channel_id=log_channel_id,
            message_id=message_id,
            ticket_details_message_id=ticket_details_message_id,
        )

    async def delete_ticket(self, ticket_id: int) -> None:
        await self.execute("DELETE FROM tickets WHERE ticket_id = ?", (ticket_id,))

    async def update_ticket_message_id(self, ticket_id: int, message_id: int) -> None:
        await self.execute(
            "UPDATE tickets SET message_id = ? WHERE ticket_id = ?", (message_id, ticket_id)
        )

    async def update_ticket_submission(self, ticket_id: int, submission_json: dict) -> None:
        await self.execute(
            "UPDATE tickets SET submission_json = ? WHERE ticket_id = ?",
            (json.dumps(submission_json), ticket_id),
        )

    async def set_ticket_claimer(self, claimer: int, ticket_id: int, guild_id: int) -> bool:
        """Atomic claim; False if somebody else claimed it first."""
        await self.ensure_member(claimer, guild_id)

        updated = await self.execute(
            "UPDATE tickets SET claimer_user_id = ? WHERE ticket_id = ? AND claimer_user_id IS NULL",
            (claimer, ticket_id),
            row_count=True,
        )
        return updated == 1

    async def reset_ticket_claimer(self, ticket_id: int) -> None:
        await self.execute(
            "UPDATE tickets SET claimer_user_id = NULL WHERE ticket_id = ?", (ticket_id,)
        )

    async def create_ticket_log(
        self,
        guild_id: int,
        opened_user_id: int,
        staff_handled: int | None,
        reason: str | None,
        ticket_type: str,
        transcripts_reference: int | None,
        transcript_channel: int,
    ) -> TicketLog:
        """Prefers the secondary (supplementary) guild when one is connected."""
        timestamp = datetime.now(UTC).isoformat()

        await self.ensure_member(opened_user_id, guild_id)
        if staff_handled:
            await self.ensure_staff(staff_handled, guild_id)

        log_id = await self.execute(
            """
            INSERT INTO ticket_logs (
                guild_id, opened_user_id, staff_handled, reason,
                ticket_type, timestamp, transcripts_reference, logs_channel_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id, opened_user_id, staff_handled, reason, ticket_type,
                timestamp, transcripts_reference, transcript_channel,
            ),
        )
        return TicketLog(
            id=log_id,  # type: ignore[arg-type]
            guild_id=guild_id,
            opened_user_id=opened_user_id,
            staff_handled=staff_handled,
            reason=reason,
            ticket_type=ticket_type,
            timestamp=timestamp,
            transcripts_reference=transcripts_reference,
            logs_channel_id=transcript_channel,
        )

    async def get_ticket_log(self, id: int, guild_id: int) -> TicketLog | None:
        row = await self.fetch_one(
            """
            SELECT id, guild_id, opened_user_id, staff_handled, reason, ticket_type,
                   timestamp, transcripts_reference, logs_channel_id
            FROM ticket_logs
            WHERE id = ? AND guild_id = ?
            """,
            (id, guild_id),
        )
        return TicketLog.from_row(row) if row else None

    async def get_ticket_logs(
        self,
        guild_id: int,
        *,
        opened_user_id: int | None = None,
        staff_handled: int | None = None,
        ticket_type: str | None = None,
        page: int = 1,
        page_size: int = 3,
    ) -> Page[TicketLog]:
        conditions = ["guild_id = ?"]
        params: list[Any] = [guild_id]

        if opened_user_id is not None:
            conditions.append("opened_user_id = ?")
            params.append(opened_user_id)
        if staff_handled is not None:
            conditions.append("staff_handled = ?")
            params.append(staff_handled)
        if ticket_type is not None:
            conditions.append("ticket_type = ?")
            params.append(ticket_type)

        where_clause = " AND ".join(conditions)

        count_row = await self.fetch_one(
            f"SELECT COUNT(*) AS total FROM ticket_logs WHERE {where_clause}", tuple(params)
        )
        rows = await self.fetch_all(
            f"""
            SELECT id, guild_id, opened_user_id, staff_handled, reason, ticket_type,
                   timestamp, transcripts_reference, logs_channel_id
            FROM ticket_logs
            WHERE {where_clause}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params) + (page_size, (page - 1) * page_size),
        )

        return Page(
            items=[TicketLog.from_row(row) for row in rows],
            page=page,
            page_size=page_size,
            total_count=count_row["total"] if count_row else 0,
        )

    async def get_ticket_types(self, guild_id: int) -> list[str]:
        rows = await self.fetch_all(
            """
            SELECT DISTINCT ticket_type
            FROM ticket_logs
            WHERE guild_id = ? AND ticket_type IS NOT NULL
            """,
            (guild_id,),
        )
        return [row["ticket_type"] for row in rows]

    async def ticket_stats(self, guild_id: int, staff_id: int) -> dict[str, int]:
        rows = await self.fetch_all(
            """
            SELECT ticket_type, COUNT(*) AS count
            FROM ticket_logs
            WHERE staff_handled = ? AND guild_id = ?
            GROUP BY ticket_type
            """,
            (staff_id, guild_id),
        )
        return {row["ticket_type"].replace("_", " ").title(): row["count"] for row in rows}

    # ----------------------------------------------------------------------- #
    # Staff
    # ----------------------------------------------------------------------- #

    async def ensure_staff(self, staff_id: int, guild_id: int) -> None:
        await self.ensure_member(member_id=staff_id, guild_id=guild_id)
        await self.execute(
            """
            INSERT OR IGNORE INTO staffs (staff_id, guild_id, name, stale)
            VALUES (?, ?, 'Unknown', 1)
            """,
            (staff_id, guild_id),
        )

    async def get_staff(self, staff_id: int, guild_id: int) -> Staff | None:
        row = await self.fetch_one(
            """
            SELECT staff_id, guild_id, name, joined_on, on_loa, retired, stale,
                   responsibility, avatar_url
            FROM staffs
            WHERE staff_id = ? AND guild_id = ?
            """,
            (staff_id, guild_id),
        )
        return Staff.from_row(row) if row else None

    async def get_staff_profile(self, staff_id: int, guild_id: int) -> StaffProfile | None:
        row = await self.fetch_one(
            """
            SELECT
                s.staff_id, s.guild_id, s.name, s.joined_on, s.on_loa, s.retired, s.stale,
                s.responsibility,
                m.avatar_url AS avatar_url,
                m.timezone AS timezone,
                GROUP_CONCAT(DISTINCT sr.role_id) AS role_ids,
                (
                    SELECT COUNT(*) FROM strikes k
                    WHERE k.guild_id = s.guild_id AND k.issued_to_id = s.staff_id
                ) AS strikes_count
            FROM staffs s
            LEFT JOIN staff_roles sr
                ON sr.staff_id = s.staff_id AND sr.guild_id = s.guild_id
            LEFT JOIN members m
                ON m.member_id = s.staff_id AND m.guild_id = s.guild_id
            WHERE s.staff_id = ? AND s.guild_id = ?
            GROUP BY s.staff_id, s.guild_id
            """,
            (staff_id, guild_id),
        )
        return StaffProfile.from_row(row) if row else None

    async def fetch_all_staffs(self, guild_id: int) -> StaffOverview:
        count_rows = await self.fetch_all(
            """
            SELECT
                r.role_type,
                COUNT(DISTINCT CASE WHEN s.retired = 0 THEN s.staff_id END) AS total_staffs,
                COUNT(DISTINCT CASE WHEN s.retired = 0 AND s.on_loa = 1 THEN s.staff_id END) AS loa_staffs,
                COUNT(DISTINCT CASE WHEN s.retired = 0 AND s.on_loa = 0 THEN s.staff_id END) AS active_staffs
            FROM staff_ranks srk
            JOIN roles r
                ON r.guild_id = srk.guild_id AND r.role_id = srk.role_id
            LEFT JOIN staff_roles sr
                ON sr.guild_id = srk.guild_id AND sr.role_id = srk.role_id
            LEFT JOIN staffs s
                ON s.guild_id = sr.guild_id AND s.staff_id = sr.staff_id
            WHERE srk.guild_id = ?
            GROUP BY r.role_type
            """,
            (guild_id,),
        )

        rows = await self.fetch_all(
            """
            SELECT
                srk.priority, srk.guild_id, r.role_id, r.role_type,
                s.staff_id, s.name, s.joined_on, s.on_loa, s.retired, s.stale, s.responsibility,
                m.avatar_url, m.timezone
            FROM staff_ranks srk
            JOIN roles r
                ON r.guild_id = srk.guild_id AND r.role_id = srk.role_id
            LEFT JOIN staff_roles sr
                ON sr.guild_id = srk.guild_id AND sr.role_id = srk.role_id
            LEFT JOIN staffs s
                ON s.guild_id = sr.guild_id AND s.staff_id = sr.staff_id AND s.retired = 0
            LEFT JOIN members m
                ON m.guild_id = s.guild_id AND m.member_id = s.staff_id
            WHERE srk.guild_id = ?
            ORDER BY srk.priority, s.name
            """,
            (guild_id,),
        )

        groups: dict[int, RoleStaffGroup] = {}
        for row in rows:
            group = groups.setdefault(
                row["role_id"],
                RoleStaffGroup(
                    role_id=row["role_id"], role_type=row["role_type"], priority=row["priority"]
                ),
            )
            if row["staff_id"] is not None:
                group.staff.append(StaffProfile.from_row(row))

        return StaffOverview(
            counts={row["role_type"]: StaffCounts.from_row(row) for row in count_rows},
            roles=list(groups.values()),
        )

    async def fetch_staff_summary(self, guild_id: int) -> StaffCounts:
        row = await self.fetch_one(
            """
            SELECT
                COUNT(DISTINCT CASE WHEN s.retired = 0 THEN s.staff_id END) AS total_staffs,
                COUNT(DISTINCT CASE WHEN s.retired = 0 AND s.on_loa = 1 THEN s.staff_id END) AS loa_staffs,
                COUNT(DISTINCT CASE WHEN s.retired = 0 AND s.on_loa = 0 THEN s.staff_id END) AS active_staffs
            FROM staff_ranks srk
            JOIN roles r
                ON r.guild_id = srk.guild_id AND r.role_id = srk.role_id
            LEFT JOIN staff_roles sr
                ON sr.guild_id = srk.guild_id AND sr.role_id = srk.role_id
            LEFT JOIN staffs s
                ON s.guild_id = sr.guild_id AND s.staff_id = sr.staff_id
            WHERE srk.guild_id = ?
            """,
            (guild_id,),
        )
        return StaffCounts.from_row(row) if row else StaffCounts()

    async def fetch_staffs_from_rank(
        self, guild_id: int, role_id: int, page_size: int = 5, page: int = 1
    ) -> Page[StaffProfile]:
        count_row = await self.fetch_one(
            """
            SELECT COUNT(*) AS total
            FROM staff_roles sr
            JOIN staffs s ON s.staff_id = sr.staff_id AND s.guild_id = sr.guild_id
            WHERE sr.guild_id = ? AND sr.role_id = ? AND s.retired = 0
            """,
            (guild_id, role_id),
        )
        rows = await self.fetch_all(
            """
            SELECT s.staff_id, s.guild_id, s.name, s.joined_on, s.on_loa, s.retired, s.stale,
                   s.responsibility, m.avatar_url, m.timezone
            FROM staff_roles sr
            JOIN staffs s ON s.staff_id = sr.staff_id AND s.guild_id = sr.guild_id
            LEFT JOIN members m ON m.member_id = s.staff_id AND m.guild_id = s.guild_id
            WHERE sr.guild_id = ? AND sr.role_id = ? AND s.retired = 0
            ORDER BY s.name
            LIMIT ? OFFSET ?
            """,
            (guild_id, role_id, page_size, (page - 1) * page_size),
        )

        return Page(
            items=[StaffProfile.from_row(row) for row in rows],
            page=page,
            page_size=page_size,
            total_count=count_row["total"] if count_row else 0,
        )

    async def fetch_loa_staffs(self, guild_id: int, role_type: str) -> list[Staff]:
        rows = await self.fetch_all(
            """
            SELECT DISTINCT s.staff_id, s.guild_id, s.name, s.joined_on, s.on_loa, s.retired,
                            s.stale, s.responsibility, s.avatar_url
            FROM staffs s
            JOIN staff_roles sr ON s.staff_id = sr.staff_id AND s.guild_id = sr.guild_id
            JOIN roles r        ON sr.role_id = r.role_id   AND sr.guild_id = r.guild_id
            WHERE s.on_loa = 1 AND s.guild_id = ? AND r.role_type = ?
            """,
            (guild_id, role_type),
        )
        return [Staff.from_row(row) for row in rows]

    async def assert_staff_role_permission(
        self, staff_id: int, updated_by: int, guild_id: int
    ) -> int:
        """Raises ``LilyError`` unless ``updated_by`` outranks ``staff_id``.

        Lower priority number = higher rank (0 = management). Returns the updater's priority.
        """
        target_rows = await self.fetch_all(
            """
            SELECT srk.priority
            FROM staff_roles sr
            JOIN roles r
                ON sr.role_id = r.role_id AND sr.guild_id = r.guild_id
            LEFT JOIN staff_ranks srk
                ON srk.role_id = r.role_id AND srk.guild_id = r.guild_id
            WHERE sr.staff_id = ? AND sr.guild_id = ? AND r.role_type = 'staff'
            """,
            (staff_id, guild_id),
        )
        if not target_rows:
            raise LilyError(f"Target user <@{staff_id}> has no assigned staff roles.")

        target_priorities = [r["priority"] for r in target_rows if r["priority"] is not None]
        if not target_priorities:
            raise LilyError(
                f"Target user <@{staff_id}> has staff roles, but none of them have a rank configured."
            )

        updater_row = await self.fetch_one(
            """
            SELECT srk.priority
            FROM staff_roles sr
            JOIN roles r
                ON sr.role_id = r.role_id AND sr.guild_id = r.guild_id
            JOIN staff_ranks srk
                ON srk.role_id = r.role_id AND srk.guild_id = r.guild_id
            WHERE sr.staff_id = ? AND sr.guild_id = ? AND r.role_type = 'staff'
            ORDER BY srk.priority ASC
            LIMIT 1
            """,
            (updated_by, guild_id),
        )
        if not updater_row:
            raise LilyError(f"Updater <@{updated_by}> has no ranked staff roles.")

        if min(target_priorities) <= updater_row["priority"]:
            raise LilyError(
                "You cannot perform this action on a staff member with an equal or higher rank."
            )
        return updater_row["priority"]

    async def add_staff(
        self,
        staff_id: int,
        guild_id: int,
        name: str,
        avatar_url: str,
        role_id: int | None = None,
    ) -> StaffRoleChanges:
        await self.ensure_member(staff_id, guild_id)
        existing = await self.get_staff(staff_id, guild_id)

        if role_id is not None and role_id not in await self.get_staff_ranks(guild_id):
            raise LilyError("The given role is not a valid staff rank.")
        if existing and not (existing.retired or existing.stale):
            raise LilyError("Staff entry already exists")

        today = datetime.now().strftime("%d/%m/%Y")

        if existing:
            await self.execute(
                """
                UPDATE staffs
                SET retired = 0, stale = 0, name = ?, avatar_url = ?, joined_on = ?
                WHERE staff_id = ? AND guild_id = ?
                """,
                (name, avatar_url, today, staff_id, guild_id),
            )
        else:
            await self.execute(
                """
                INSERT INTO staffs (
                    staff_id, name, guild_id, on_loa, retired, stale,
                    responsibility, avatar_url, joined_on
                )
                VALUES (?, ?, ?, 0, 0, 0, 'None', ?, ?)
                """,
                (staff_id, name, guild_id, avatar_url, today),
            )

        initial_role = role_id
        if initial_role is None:
            lowest = await self.fetch_one(
                """
                SELECT r.role_id
                FROM roles r
                JOIN staff_ranks srk
                    ON srk.guild_id = r.guild_id AND srk.role_id = r.role_id
                WHERE r.guild_id = ? AND r.role_type = 'staff'
                ORDER BY srk.priority DESC
                LIMIT 1
                """,
                (guild_id,),
            )
            initial_role = lowest["role_id"] if lowest else None

        roles_to_add = set(await self.get_role_of_type(guild_id, "staff_base"))
        if initial_role is not None:
            await self.execute(
                "INSERT OR IGNORE INTO staff_roles (staff_id, guild_id, role_id) VALUES (?, ?, ?)",
                (staff_id, guild_id, initial_role),
            )
            roles_to_add.add(initial_role)

        staff = await self.get_staff(staff_id, guild_id)
        assert staff is not None
        return StaffRoleChanges(staff=staff, roles_to_add=list(roles_to_add))

    async def remove_staff(self, staff_id: int, guild_id: int) -> StaffRoleChanges:
        staff = await self.get_staff(staff_id, guild_id)
        if staff is None:
            raise LilyError("Staff not found")
        if staff.retired:
            raise LilyError("Staff is already retired")

        await self.execute(
            "UPDATE staffs SET retired = 1 WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        )

        role_rows = await self.fetch_all(
            "SELECT role_id FROM staff_roles WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        )
        roles_to_remove = {r["role_id"] for r in role_rows}
        roles_to_remove.update(await self.get_role_of_type(guild_id, "staff_base"))

        await self.execute(
            "DELETE FROM staff_roles WHERE staff_id = ? AND guild_id = ?", (staff_id, guild_id)
        )
        return StaffRoleChanges(
            staff=replace(staff, retired=True), roles_to_remove=list(roles_to_remove)
        )

    async def edit_staff(
        self,
        staff_id: int,
        guild_id: int,
        name: Optional[str],
        joined_on: Optional[str],
        timezone: Optional[str],
        responsibility: Optional[str],
    ) -> Edit[StaffProfile]:
        before = await self.get_staff_profile(staff_id, guild_id)
        if before is None:
            raise LilyError(f"No staff found with ID {staff_id}")

        fields = {
            k: v
            for k, v in {"name": name, "joined_on": joined_on, "responsibility": responsibility}.items()
            if v is not None
        }
        if not fields and not timezone:
            raise LilyError("No fields provided to update")

        if fields:
            await self.execute(
                f"""
                UPDATE staffs
                SET {", ".join(f"{k} = ?" for k in fields)}
                WHERE staff_id = ? AND guild_id = ?
                """,
                (*fields.values(), staff_id, guild_id),
            )

        if timezone:
            await self.ensure_member(staff_id, guild_id)
            await self.execute(
                "UPDATE members SET timezone = ? WHERE member_id = ? AND guild_id = ?",
                (timezone, staff_id, guild_id),
            )

        after = await self.get_staff_profile(staff_id, guild_id)
        assert after is not None
        return Edit(before=before, after=after)

    async def update_staff(
        self,
        guild_id: int,
        staff_id: int,
        update_type: str,
        reason: str,
        updated_by: int,
        elevated: bool = False,
        rank_id: int | None = None,
    ) -> RankUpdate:
        if staff_id == updated_by and not elevated:
            raise LilyError("You cannot update yourself.")
        if update_type not in ("promotion", "demotion"):
            raise LilyError("Invalid update_type.")
        promotion = update_type == "promotion"

        current = await self.fetch_one(
            """
            SELECT sr.role_id, srk.priority
            FROM staff_roles sr
            JOIN roles r
                ON sr.role_id = r.role_id AND sr.guild_id = r.guild_id
            JOIN staff_ranks srk
                ON srk.role_id = r.role_id AND srk.guild_id = r.guild_id
            WHERE sr.staff_id = ? AND sr.guild_id = ? AND r.role_type = 'staff'
            ORDER BY srk.priority ASC
            LIMIT 1
            """,
            (staff_id, guild_id),
        )
        if not current:
            raise LilyError("No ranked staff role assigned.")

        updater_priority = (
            None
            if elevated
            else await self.assert_staff_role_permission(staff_id, updated_by, guild_id)
        )

        if rank_id is not None:
            target = await self.fetch_one(
                """
                SELECT r.role_id, srk.priority
                FROM roles r
                JOIN staff_ranks srk
                    ON srk.role_id = r.role_id AND srk.guild_id = r.guild_id
                WHERE r.guild_id = ? AND r.role_type = 'staff' AND r.role_id = ?
                LIMIT 1
                """,
                (guild_id, rank_id),
            )
            if not target:
                raise LilyError("The given role is not a valid staff rank.")
            if promotion and target["priority"] >= current["priority"]:
                raise LilyError("That rank is not higher than the staff member's current rank.")
            if not promotion and target["priority"] <= current["priority"]:
                raise LilyError("That rank is not lower than the staff member's current rank.")
        else:
            operator, order = ("<", "DESC") if promotion else (">", "ASC")
            target = await self.fetch_one(
                f"""
                SELECT r.role_id, srk.priority
                FROM roles r
                JOIN staff_ranks srk
                    ON srk.role_id = r.role_id AND srk.guild_id = r.guild_id
                WHERE r.guild_id = ? AND r.role_type = 'staff' AND srk.priority {operator} ?
                ORDER BY srk.priority {order}
                LIMIT 1
                """,
                (guild_id, current["priority"]),
            )
            if not target:
                raise LilyError(f"Already at {'highest' if promotion else 'lowest'} role.")

        if updater_priority is not None and target["priority"] < updater_priority:
            raise LilyError("You cannot update someone beyond your own role priority.")
        if target["role_id"] == current["role_id"]:
            raise LilyError("Staff already holds that rank.")

        await self.execute(
            """
            UPDATE staff_roles
            SET role_id = ?
            WHERE staff_id = ? AND guild_id = ? AND role_id = ?
            """,
            (target["role_id"], staff_id, guild_id, current["role_id"]),
        )
        update_id = await self.execute(
            """
            INSERT INTO rank_updates (
                guild_id, staff_id, updated_by, old_role_id, new_role_id, update_type, reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, staff_id, updated_by, current["role_id"], target["role_id"], update_type, reason),
        )

        row = await self.fetch_one(
            """
            SELECT id, guild_id, staff_id, updated_by, update_type,
                   old_role_id, new_role_id, reason, timestamp
            FROM rank_updates
            WHERE id = ?
            """,
            (update_id,),
        )
        return RankUpdate.from_row(row)

    async def get_rank_updates(
        self,
        guild_id: int,
        *,
        staff_id: int | None = None,
        updated_by: int | None = None,
        update_type: str | None = None,
        old_role_id: int | None = None,
        new_role_id: int | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        page: int = 1,
        page_size: int = 5,
    ) -> Page[RankUpdate]:
        conditions = ["guild_id = ?"]
        params: list[Any] = [guild_id]

        for column, value in (
            ("staff_id", staff_id),
            ("updated_by", updated_by),
            ("update_type", update_type),
            ("old_role_id", old_role_id),
            ("new_role_id", new_role_id),
        ):
            if value is not None:
                conditions.append(f"{column} = ?")
                params.append(value)

        if after is not None:
            conditions.append("timestamp >= ?")
            params.append(after.strftime("%Y-%m-%d %H:%M:%S"))
        if before is not None:
            conditions.append("timestamp < ?")
            params.append(before.strftime("%Y-%m-%d %H:%M:%S"))

        where_clause = " AND ".join(conditions)

        count_row = await self.fetch_one(
            f"SELECT COUNT(*) AS total FROM rank_updates WHERE {where_clause}", tuple(params)
        )
        rows = await self.fetch_all(
            f"""
            SELECT id, guild_id, staff_id, updated_by, update_type,
                   old_role_id, new_role_id, reason, timestamp
            FROM rank_updates
            WHERE {where_clause}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params) + (page_size, (page - 1) * page_size),
        )

        return Page(
            items=[RankUpdate.from_row(row) for row in rows],
            page=page,
            page_size=page_size,
            total_count=count_row["total"] if count_row else 0,
        )

    # ----------------------------------------------------------------------- #
    # Strikes
    # ----------------------------------------------------------------------- #

    async def strike_staff(
        self,
        staff_id: int,
        guild_id: int,
        issued_by: int,
        reason: str,
        type: str,
        expiry_date: str,
    ) -> Strike:
        """``expiry_date`` is ``"none"`` or ``"<days>d"`` (e.g. ``"30d"``)."""
        await self.ensure_staff(issued_by, guild_id)
        await self.ensure_staff(staff_id, guild_id)
        await self.assert_staff_role_permission(staff_id, issued_by, guild_id)

        now = datetime.now(UTC)
        expires_on = (
            None
            if expiry_date == "none"
            else (now + timedelta(days=int(expiry_date[:-1]))).isoformat()
        )

        strike_id = await self.execute(
            """
            INSERT INTO strikes (issued_by_id, issued_to_id, reason, date, guild_id, type, expiry_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (issued_by, staff_id, reason, now.isoformat(), guild_id, type, expires_on),
        )
        return Strike(
            id=strike_id,  # type: ignore[arg-type]
            guild_id=guild_id,
            issued_by_id=issued_by,
            issued_to_id=staff_id,
            reason=reason,
            date=now.isoformat(),
            expiry_date=expires_on,
            type=type,
        )

    async def get_strike(self, strike_id: int, guild_id: int) -> Strike | None:
        row = await self.fetch_one(
            """
            SELECT strike_id, guild_id, issued_by_id, issued_to_id, reason, date, expiry_date, type
            FROM strikes
            WHERE strike_id = ? AND guild_id = ?
            """,
            (strike_id, guild_id),
        )
        return Strike.from_row(row) if row else None

    async def remove_strike(self, strike_id: int, guild_id: int) -> Strike:
        strike = await self.get_strike(strike_id, guild_id)
        if strike is None:
            raise LilyError(f"No strike with ID `{strike_id}` found")

        await self.execute(
            "DELETE FROM strikes WHERE strike_id = ? AND guild_id = ?", (strike_id, guild_id)
        )
        return strike

    async def edit_strike(
        self, strike_id: int, guild_id: int, staff_id: int, new_reason: str
    ) -> Edit[Strike]:
        before = await self.get_strike(strike_id, guild_id)
        if before is None:
            raise LilyError(f"No strike with ID `{strike_id}` found")
        if before.issued_by_id != staff_id:
            raise LilyError("Only the staff who issued the strike can edit it.")

        await self.execute(
            "UPDATE strikes SET reason = ? WHERE strike_id = ? AND guild_id = ?",
            (new_reason, strike_id, guild_id),
        )
        return Edit(before=before, after=replace(before, reason=new_reason))

    async def get_strike_types(self, guild_id: int) -> list[str]:
        rows = await self.fetch_all(
            "SELECT DISTINCT type FROM strikes WHERE type IS NOT NULL AND guild_id = ?",
            (guild_id,),
        )
        return [row[0] for row in rows]

    async def fetch_staff_strikes(
        self, staff_id: int, guild_id: int, *, page: int = 1, page_size: int = 3
    ) -> Page[Strike]:
        count_row = await self.fetch_one(
            "SELECT COUNT(*) AS total FROM strikes WHERE issued_to_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        )
        rows = await self.fetch_all(
            """
            SELECT strike_id, guild_id, issued_by_id, issued_to_id, reason, date, expiry_date, type
            FROM strikes
            WHERE issued_to_id = ? AND guild_id = ?
            ORDER BY strike_id DESC
            LIMIT ? OFFSET ?
            """,
            (staff_id, guild_id, page_size, (page - 1) * page_size),
        )

        return Page(
            items=[Strike.from_row(row) for row in rows],
            page=page,
            page_size=page_size,
            total_count=count_row["total"] if count_row else 0,
        )

    # ----------------------------------------------------------------------- #
    # LOA
    # ----------------------------------------------------------------------- #

    async def add_loa(
        self, guild_id: int, staff_id: int, reason: str, loa_issued_by: int
    ) -> StaffRoleChanges:
        if not staff_id:
            raise LilyError("Missing staff_id")
        if staff_id == loa_issued_by:
            raise LilyError("You cannot assign LOA to yourself")

        staff = await self.get_staff(staff_id, guild_id)
        if staff is None:
            raise LilyError("Staff not found")
        if staff.on_loa:
            raise LilyError("Staff is already on LOA")

        await self.assert_staff_role_permission(staff_id, loa_issued_by, guild_id)

        await self.execute(
            "UPDATE staffs SET on_loa = 1 WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        )

        started_on = datetime.now(UTC).isoformat()
        leave_id = await self.execute(
            """
            INSERT INTO leaves (staff_id, reason, issued_by, guild_id, started_on)
            VALUES (?, ?, ?, ?, ?)
            """,
            (staff_id, reason, loa_issued_by, guild_id, started_on),
        )

        role_rows = await self.fetch_all(
            "SELECT role_id FROM staff_roles WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        )
        roles_to_remove = [r["role_id"] for r in role_rows]
        roles_to_remove += await self.get_role_of_type(guild_id, "staff_base")

        return StaffRoleChanges(
            staff=replace(staff, on_loa=True),
            roles_to_add=await self.get_role_of_type(guild_id, "staff_loa"),
            roles_to_remove=roles_to_remove,
            leave=Leave(
                id=leave_id,  # type: ignore[arg-type]
                guild_id=guild_id,
                staff_id=staff_id,
                issued_by=loa_issued_by,
                reason=reason,
                started_on=started_on,
            ),
        )

    async def remove_loa(self, staff_id: int, guild_id: int) -> StaffRoleChanges:
        if not staff_id:
            raise LilyError("Missing staff_id")

        staff = await self.get_staff(staff_id, guild_id)
        if staff is None:
            raise LilyError("Staff not found")
        if not staff.on_loa:
            raise LilyError("Staff is not on LOA")

        await self.execute(
            "UPDATE staffs SET on_loa = 0 WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        )

        leave_row = await self.fetch_one(
            """
            SELECT leave_id, guild_id, staff_id, issued_by, reason, days, started_on, ended_on
            FROM leaves
            WHERE staff_id = ? AND guild_id = ?
            ORDER BY leave_id DESC
            LIMIT 1
            """,
            (staff_id, guild_id),
        )
        leave = Leave.from_row(leave_row) if leave_row else None
        if leave:
            ended_on = datetime.now(UTC).isoformat()
            await self.execute(
                "UPDATE leaves SET ended_on = ? WHERE leave_id = ?", (ended_on, leave.id)
            )
            leave = replace(leave, ended_on=ended_on)

        role_rows = await self.fetch_all(
            "SELECT role_id FROM staff_roles WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        )
        roles_to_add = [r["role_id"] for r in role_rows]
        roles_to_add += await self.get_role_of_type(guild_id, "staff_base")

        return StaffRoleChanges(
            staff=replace(staff, on_loa=False),
            roles_to_add=roles_to_add,
            roles_to_remove=await self.get_role_of_type(guild_id, "staff_loa"),
            leave=leave,
        )

    async def loa_list(self, staff_id: int, guild_id: int) -> list[Leave]:
        rows = await self.fetch_all(
            """
            SELECT leave_id, guild_id, staff_id, issued_by, reason, days, started_on, ended_on
            FROM leaves
            WHERE staff_id = ? AND guild_id = ?
            ORDER BY leave_id DESC
            """,
            (staff_id, guild_id),
        )
        return [Leave.from_row(row) for row in rows]

    async def delete_loa(self, leave_id: int) -> None:
        await self.execute("DELETE FROM leaves WHERE leave_id = ?", (leave_id,))

    async def add_loa_pending(
        self, staff_id: int, guild_id: int, message_id: int, reason: str, days: str
    ) -> None:
        await self.ensure_staff(staff_id, guild_id)
        await self.execute(
            """
            INSERT INTO leaves_pending (staff_id, guild_id, message_id, reason, days)
            VALUES (?, ?, ?, ?, ?)
            """,
            (staff_id, guild_id, message_id, reason, days),
        )

    async def get_loa_pending(self, staff_id: int, guild_id: int) -> PendingLeave | None:
        row = await self.fetch_one(
            """
            SELECT lp.id, lp.staff_id, lp.guild_id, lp.message_id, lp.reason, lp.days,
                   m.avatar_url
            FROM leaves_pending lp
            LEFT JOIN members m
                ON lp.staff_id = m.member_id AND lp.guild_id = m.guild_id
            WHERE lp.staff_id = ? AND lp.guild_id = ?
            LIMIT 1
            """,
            (staff_id, guild_id),
        )
        return PendingLeave.from_row(row) if row else None

    async def fetch_all_loa_pending(self) -> list[PendingLeave]:
        rows = await self.fetch_all(
            """
            SELECT lp.id, lp.staff_id, lp.guild_id, lp.message_id, lp.reason, lp.days,
                   m.avatar_url
            FROM leaves_pending lp
            LEFT JOIN members m
                ON lp.staff_id = m.member_id AND lp.guild_id = m.guild_id
            """
        )
        return [PendingLeave.from_row(row) for row in rows]

    async def delete_loa_pending(self, staff_id: int, guild_id: int) -> None:
        await self.execute(
            "DELETE FROM leaves_pending WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        )

    # ----------------------------------------------------------------------- #
    # Quotas
    # ----------------------------------------------------------------------- #

    async def add_staff_quota(
        self, guild_id: int, role_id: int, min_msg: int, min_ms: int, check_by: str
    ) -> StaffQuota:
        if check_by not in ("1d", "7d", "30d", None):
            raise LilyError("Invalid parameter type passed (check_by)")

        quota_id = await self.execute(
            """
            INSERT INTO staff_quota (role_id, guild_id, min_msg, min_ms, check_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (role_id, guild_id, min_msg, min_ms, check_by),
        )
        return StaffQuota(
            id=quota_id,  # type: ignore[arg-type]
            guild_id=guild_id,
            role_id=role_id,
            min_msg=min_msg,
            min_ms=min_ms,
            check_by=check_by,
        )

    async def get_quotas(
        self,
        guild_id: int | None = None,
        *,
        quota_id: int | None = None,
        role_id: int | None = None,
        check_by: str | None = None,
    ) -> list[StaffQuota]:
        """All quotas matching the given filters (no filter = every quota in every guild)."""
        conditions, params = [], []
        for column, value in (
            ("guild_id", guild_id),
            ("quota_id", quota_id),
            ("role_id", role_id),
            ("check_by", check_by),
        ):
            if value is not None:
                conditions.append(f"{column} = ?")
                params.append(value)

        rows = await self.fetch_all(
            f"""
            SELECT quota_id, guild_id, role_id, min_msg, min_ms,
                   on_quota_passed, on_quota_failed, check_by
            FROM staff_quota
            {'WHERE ' + ' AND '.join(conditions) if conditions else ''}
            ORDER BY quota_id
            """,
            tuple(params),
        )
        return [StaffQuota.from_row(row) for row in rows]

    async def remove_staff_quota(self, guild_id: int, quota_id: int) -> StaffQuota:
        quotas = await self.get_quotas(guild_id, quota_id=quota_id)
        if not quotas:
            raise LilyError(f"No quota found with id {quota_id} for this guild")

        await self.execute(
            "DELETE FROM staff_quota WHERE quota_id = ? AND guild_id = ?", (quota_id, guild_id)
        )
        return quotas[0]

    async def evaluate_quotas(
        self, guild_id: int, *, staff_id: int | None = None, quota_id: int | None = None
    ) -> list[QuotaResult]:
        """One ``QuotaResult`` per (staff, applicable quota).

        * ``staff_id`` given  -> that staff only (LOA allowed, retired raises).
        * ``quota_id`` given  -> only that quota.
        * neither             -> every active, non-LOA staff against every quota.
        Each quota is judged over its own ``check_by`` period (default 7d).
        """
        conditions = ["q.guild_id = ?", "s.retired = 0"]
        params: list[Any] = [guild_id]

        if staff_id is not None:
            staff = await self.get_staff(staff_id, guild_id)
            if staff is None or staff.retired:
                raise LilyError("This user is not an active staff member.")
            conditions.append("s.staff_id = ?")
            params.append(staff_id)
        else:
            conditions.append("s.on_loa = 0")

        if quota_id is not None:
            conditions.append("q.quota_id = ?")
            params.append(quota_id)

        rows = await self.fetch_all(
            f"""
            SELECT
                s.staff_id, s.guild_id, s.name, s.joined_on, s.on_loa, s.retired, s.stale,
                s.responsibility, s.avatar_url,
                q.quota_id, q.role_id, q.min_msg, q.min_ms,
                q.on_quota_passed, q.on_quota_failed, q.check_by,
                COALESCE(msg.daily_messages, 0)   AS daily_messages,
                COALESCE(msg.weekly_messages, 0)  AS weekly_messages,
                COALESCE(msg.monthly_messages, 0) AS monthly_messages
            FROM staff_quota q
            JOIN staff_roles sr
                ON sr.guild_id = q.guild_id AND sr.role_id = q.role_id
            JOIN staffs s
                ON s.guild_id = sr.guild_id AND s.staff_id = sr.staff_id
            LEFT JOIN messages msg
                ON msg.guild_id = s.guild_id AND msg.member_id = s.staff_id
            WHERE {' AND '.join(conditions)}
            ORDER BY s.staff_id, q.quota_id
            """,
            tuple(params),
        )

        message_columns = {"1d": "daily_messages", "7d": "weekly_messages", "30d": "monthly_messages"}
        mod_stats: dict[int, ModStats] = {}
        results: list[QuotaResult] = []

        for row in rows:
            quota = StaffQuota.from_row(row)
            staff = Staff.from_row(row)

            period = (quota.check_by or "7d").strip().lower()
            if period not in message_columns:
                period = "7d"

            if staff.id not in mod_stats:
                mod_stats[staff.id] = await self.fetch_mod_stats(guild_id, staff.id)

            results.append(
                QuotaResult(
                    quota=quota,
                    staff=staff,
                    period=period,  # type: ignore[arg-type]
                    messages=int(row[message_columns[period]]),
                    mod_stats=mod_stats[staff.id].count(period),  # type: ignore[arg-type]
                )
            )

        return results

    async def create_quota_history(
        self,
        quota_id: int,
        staff_id: int,
        guild_id: int,
        status: Literal["pass", "fail"],
        timestamp: str,
    ) -> StaffQuotaHistory:
        if status not in ("pass", "fail"):
            raise ValueError("status must be either 'pass' or 'fail'")

        history_id = await self.execute(
            """
            INSERT INTO staff_quota_history (quota_id, staff_id, guild_id, status, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (quota_id, staff_id, guild_id, status, timestamp),
        )
        return StaffQuotaHistory(
            id=history_id,  # type: ignore[arg-type]
            quota_id=quota_id,
            staff_id=staff_id,
            guild_id=guild_id,
            status=status,
            timestamp=timestamp,
        )

    # ----------------------------------------------------------------------- #
    # Messages / XP / leaderboard
    # ----------------------------------------------------------------------- #

    async def set_xp_boost(self, guild_id: int, role_id: int, multiplier: float) -> None:
        await self.execute(
            """
            INSERT INTO xp_boosts (guild_id, role_id, multiplier)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, role_id) DO UPDATE SET multiplier = excluded.multiplier
            """,
            (guild_id, role_id, multiplier),
        )

    async def remove_xp_boost(self, guild_id: int, role_id: int) -> None:
        await self.execute(
            "DELETE FROM xp_boosts WHERE guild_id = ? AND role_id = ?", (guild_id, role_id)
        )

    async def fetch_boosted_roles(self, guild_id: int) -> dict[int, float]:
        rows = await self.fetch_all(
            "SELECT role_id, multiplier FROM xp_boosts WHERE guild_id = ?", (guild_id,)
        )
        return {row["role_id"]: row["multiplier"] for row in rows}

    def get_xp_multiplier(
        self, member_role_ids: set[int], boosted_roles: dict[int, float]
    ) -> float:
        return max(
            (mult for role_id, mult in boosted_roles.items() if role_id in member_role_ids),
            default=1.0,
        )

    async def update_message(
        self,
        staff_id: int,
        guild_id: int,
        member_role_ids: set[int],
        boosted_roles: dict[int, float],
        avatar_url: str | None = None,
        name: str | None = None,
    ) -> LevelUp | None:
        """Update profile + message/XP counts. Returns a ``LevelUp`` if the member leveled up."""
        xp_gain = round(1 * self.get_xp_multiplier(member_role_ids, boosted_roles))

        await self.execute(
            """
            INSERT INTO members (member_id, guild_id, avatar_url, name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(member_id, guild_id)
            DO UPDATE SET avatar_url = excluded.avatar_url, name = excluded.name
            """,
            (staff_id, guild_id, avatar_url, name),
        )

        row = await self.fetch_one(
            """
            INSERT INTO messages (
                member_id, guild_id,
                daily_messages, weekly_messages, monthly_messages, total_messages, total_xp
            )
            VALUES (?, ?, 1, 1, 1, 1, ?)
            ON CONFLICT(member_id, guild_id) DO UPDATE SET
                daily_messages   = daily_messages   + 1,
                weekly_messages  = weekly_messages  + 1,
                monthly_messages = monthly_messages + 1,
                total_messages   = total_messages   + 1,
                total_xp         = total_xp         + excluded.total_xp
            RETURNING total_xp
            """,
            (staff_id, guild_id, xp_gain),
        )

        new_total_xp = row["total_xp"]
        old_level = level_from_messages(new_total_xp - xp_gain)
        new_level = level_from_messages(new_total_xp)

        if new_level > old_level:
            return LevelUp(
                old_level=old_level,
                new_level=new_level,
                progress=dict(get_level_progress(new_total_xp)),
            )
        return None

    async def reset_messages(self, type: Literal["daily", "weekly", "monthly"]) -> None:
        if type not in ("daily", "weekly", "monthly"):
            raise ValueError("type must be 'daily', 'weekly' or 'monthly'")
        await self.execute(f"UPDATE messages SET {type}_messages = 0")

    async def get_messages(self, guild_id: int, member_id: int) -> MessageCount:
        row = await self.fetch_one(
            """
            SELECT daily_messages, weekly_messages, monthly_messages, total_messages, total_xp
            FROM messages
            WHERE guild_id = ? AND member_id = ?
            """,
            (guild_id, member_id),
        )
        return MessageCount.from_row(row) if row else MessageCount()

    async def leaderboard(
        self,
        guild_id: int,
        leaderboard_type: int,
        target: int,
        page: int = 1,
        per_page: int = 10,
    ) -> Leaderboard:
        """``leaderboard_type``: 0 daily, 1 weekly, 2 monthly, 3 total."""
        column = {0: "daily_messages", 1: "weekly_messages", 2: "monthly_messages", 3: "total_messages"}.get(
            leaderboard_type
        )
        if column is None:
            raise LilyError("Invalid leaderboard type")

        page = max(1, page)
        offset = (page - 1) * per_page

        total_row = await self.fetch_one(
            "SELECT COUNT(*) AS count FROM messages WHERE guild_id = ?", (guild_id,)
        )
        rows = await self.fetch_all(
            f"""
            SELECT m.member_id, m.name, m.avatar_url, msg.{column} AS messages
            FROM messages msg
            INNER JOIN members m
                ON m.member_id = msg.member_id AND m.guild_id = msg.guild_id
            WHERE msg.guild_id = ?
            ORDER BY msg.{column} DESC
            LIMIT ? OFFSET ?
            """,
            (guild_id, per_page, offset),
        )
        target_row = await self.fetch_one(
            f"""
            SELECT member_id, name, avatar_url, messages, rank FROM (
                SELECT
                    m.member_id, m.name, m.avatar_url, msg.{column} AS messages,
                    ROW_NUMBER() OVER (ORDER BY msg.{column} DESC) AS rank
                FROM messages msg
                INNER JOIN members m
                    ON m.member_id = msg.member_id AND m.guild_id = msg.guild_id
                WHERE msg.guild_id = ?
            ) ranked
            WHERE member_id = ?
            """,
            (guild_id, target),
        )

        return Leaderboard(
            type=column.removesuffix("_messages"),
            page=Page(
                items=[
                    LeaderboardEntry(
                        rank=rank,
                        member_id=row["member_id"],
                        count=row["messages"],
                        name=row["name"],
                        avatar_url=row["avatar_url"],
                    )
                    for rank, row in enumerate(rows, start=offset + 1)
                ],
                page=page,
                page_size=per_page,
                total_count=total_row["count"] if total_row else 0,
            ),
            target=(
                LeaderboardEntry(
                    rank=target_row["rank"],
                    member_id=target_row["member_id"],
                    count=target_row["messages"],
                    name=target_row["name"],
                    avatar_url=target_row["avatar_url"],
                )
                if target_row
                else None
            ),
        )

    # ----------------------------------------------------------------------- #
    # Custom role mapping
    # ----------------------------------------------------------------------- #

    async def get_role_mapping(self, member_id: int, guild_id: int) -> list[int]:
        rows = await self.fetch_all(
            "SELECT role_id FROM roles_customize WHERE member_id = ? AND guild_id = ?",
            (member_id, guild_id),
        )
        return [row["role_id"] for row in rows]

    async def add_role_mapping(self, member_id: int, guild_id: int, role_id: int) -> None:
        await self.execute(
            """
            INSERT INTO roles_customize (member_id, guild_id, role_id)
            VALUES (?, ?, ?)
            ON CONFLICT(member_id, guild_id, role_id) DO NOTHING
            """,
            (member_id, guild_id, role_id),
        )

    async def remove_role_mapping(self, member_id: int, guild_id: int, role_id: int) -> None:
        await self.execute(
            "DELETE FROM roles_customize WHERE member_id = ? AND guild_id = ? AND role_id = ?",
            (member_id, guild_id, role_id),
        )

    # ----------------------------------------------------------------------- #
    # Analytics
    # ----------------------------------------------------------------------- #

    async def get_staffs_timezone_coverage(self, guild_id: int) -> dict[str, int]:
        rows = await self.fetch_all(
            """
            SELECT m.timezone, COUNT(*) AS count
            FROM members m
            INNER JOIN staffs s
                ON s.staff_id = m.member_id AND s.guild_id = m.guild_id
            WHERE m.timezone IS NOT NULL AND m.guild_id = ? AND s.retired = 0
            GROUP BY m.timezone
            """,
            (guild_id,),
        )
        return {row["timezone"]: row["count"] for row in rows}

    async def get_moderation_monthly_analysis(self, guild_id: int) -> dict[str, int]:
        """``{"YYYY-MM-DD": total}`` for the last 30 days, oldest first."""
        rows = await self.fetch_all(
            """
            SELECT strftime('%Y-%m-%d', timestamp) AS day, COUNT(*) AS total
            FROM modlogs
            WHERE guild_id = ? AND timestamp >= DATE('now', '-30 days')
            GROUP BY day
            ORDER BY day
            """,
            (guild_id,),
        )
        return {row["day"]: row["total"] for row in rows}

    # ----------------------------------------------------------------------- #
    # Moderation acronyms
    # ----------------------------------------------------------------------- #

    async def get_moderation_acronyms(self, member_id: int, guild_id: int) -> dict[str, str]:
        row = await self.fetch_one(
            "SELECT acronyms FROM acronyms WHERE member_id = ? AND guild_id = ?",
            (member_id, guild_id),
        )
        return json.loads(row[0] or "{}") if row else {}

    async def set_moderation_acronym(
        self, member_id: int, guild_id: int, key: str, value: str
    ) -> dict[str, str]:
        """Add or update an acronym. Returns the member's full mapping."""
        data = await self.get_moderation_acronyms(member_id, guild_id)
        data[key.lower().strip()] = value

        await self.execute(
            """
            INSERT INTO acronyms (member_id, guild_id, acronyms)
            VALUES (?, ?, ?)
            ON CONFLICT(member_id, guild_id)
            DO UPDATE SET acronyms = excluded.acronyms
            """,
            (member_id, guild_id, json.dumps(data)),
        )
        return data

    async def remove_moderation_acronym(
        self, member_id: int, guild_id: int, key: str
    ) -> dict[str, str]:
        """Returns the member's remaining mapping."""
        data = await self.get_moderation_acronyms(member_id, guild_id)
        if data.pop(key.lower().strip(), None) is None:
            raise LilyError(f"No acronym named `{key}` found")

        await self.execute(
            "UPDATE acronyms SET acronyms = ? WHERE member_id = ? AND guild_id = ?",
            (json.dumps(data), member_id, guild_id),
        )
        return data

    # ----------------------------------------------------------------------- #
    # Tags
    # ----------------------------------------------------------------------- #

    async def add_tag(self, name: str, content: str, created_by: int) -> Tag:
        name = name.strip().lower()
        created = await self.execute(
            "INSERT INTO tags (name, content, created_by) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO NOTHING",
            (name, content, created_by),
            row_count=True,
        )
        if not created:
            raise LilyError(f"Tag `{name}` already exists")
        return Tag(name=name, content=content, created_by=created_by)

    async def get_tag(self, name: str) -> Tag | None:
        row = await self.fetch_one(
            "SELECT name, content, created_by FROM tags WHERE name = ?",
            (name.strip().lower(),),
        )
        return Tag.from_row(row) if row else None

    async def update_tag(self, name: str, content: str) -> Edit[Tag]:
        before = await self.get_tag(name)
        if before is None:
            raise LilyError(f"Tag `{name.strip().lower()}` not found")

        await self.execute("UPDATE tags SET content = ? WHERE name = ?", (content, before.name))
        return Edit(before=before, after=replace(before, content=content))

    async def delete_tag(self, name: str) -> Tag:
        tag = await self.get_tag(name)
        if tag is None:
            raise LilyError(f"Tag `{name.strip().lower()}` not found")

        await self.execute("DELETE FROM tags WHERE name = ?", (tag.name,))
        return tag

    async def search_tags(
        self, query: str, limit: int = 5, score_cutoff: int = 60
    ) -> list[str]:
        rows = await self.fetch_all("SELECT name FROM tags")
        matches = process.extract(
            query.strip().lower(),
            [r["name"] for r in rows],
            scorer=fuzz.WRatio,
            limit=limit,
            score_cutoff=score_cutoff,
        )
        return [name for name, _score, _idx in matches]