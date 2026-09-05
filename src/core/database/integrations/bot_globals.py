from ..access import LilyDatabaseAccess
from .applications import ApplicationManagement
from .leveling import LevelingManagement

from typing import List, Optional, Final, Set, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, UTC
from collections import defaultdict

import json
import pytz

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


class BotGlobalsDatabaseAccess(LilyDatabaseAccess):
    def __init__(self):
        super().__init__()

        self.cache: dict[int, dict] = {}
        self.member_cache: dict[int, Any] = {}
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
                roles:       { role_id:      { limit, ban_queue,
                                               assignment_scope,
                                               assignment_roles } },
                prefix: str,
            }
        }

        """
        self.cache.clear()
        self.member_cache.clear()

        prefixes = await self.fetch_all(
            """
            SELECT member_id, guild_id , prefix FROM members WHERE prefix IS NOT NULL
            """
        )

        self.member_cache = {
            row["member_id"]: {}
            for row in prefixes
        }

        for row in prefixes:
            self.member_cache[row["member_id"]][row["guild_id"]] = row["prefix"]

        guilds = await self.fetch_all("""
            SELECT
                d.guild_id,
                d.prefix,
                gc.secondary_guild_id
            FROM data d
            LEFT JOIN guild_connections gc
                ON d.guild_id = gc.primary_guild_id
        """)

        for g in guilds:
            gid = g["guild_id"]
            self.cache[gid] = {
                "channels": {},
                "permissions": {},
                "roles": {},
                "prefix": g["prefix"] or "",
                "secondary_guild_id": g["secondary_guild_id"]
            }

        channel_rows = await self.fetch_all(
            "SELECT guild_id, channel_type, channel_id FROM guild_channels"
        )
        for row in channel_rows:
            gid = row["guild_id"]
            cache = self.cache.get(gid)
            if cache is None:
                continue
            cache["channels"].setdefault(row["channel_type"], []).append(
                row["channel_id"]
            )

        perm_rows = await self.fetch_all(
            "SELECT guild_id, role_id, command FROM permissions"
        )
        for row in perm_rows:
            gid = row["guild_id"]
            cache = self.cache.get(gid)
            if cache is None:
                continue
            cache["permissions"].setdefault(row["command"], []).append(row["role_id"])

        role_rows = await self.fetch_all(
            """
            SELECT
                r.guild_id,
                r.role_id,
                r.ban_limit,
                r.ban_queue,
                r.assignment_scope,
                ra.target_role_id
            FROM roles r
            LEFT JOIN role_assignments ra
                ON  ra.guild_id = r.guild_id
                AND ra.role_id  = r.role_id
            """
        )
        for row in role_rows:
            gid = row["guild_id"]
            cache = self.cache.get(gid)
            if cache is None:
                continue

            role_id = row["role_id"]
            if role_id not in cache["roles"]:
                cache["roles"][role_id] = {
                    "limit": row["ban_limit"] or 0,
                    "ban_queue": row["ban_queue"] or 0,
                    "assignment_scope": row["assignment_scope"] or "none",
                    "assignment_roles": set(),
                }

            if row["target_role_id"] is not None:
                cache["roles"][role_id]["assignment_roles"].add(row["target_role_id"])

        row = await self.fetch_one("SELECT value FROM globals WHERE key = 'Jail'")
        if row and row["value"]:
            self._gconfig = GlobalConfig(jail=int(row["value"]))

        self._cache_ready = True

    @property
    def global_config(self) -> Optional[GlobalConfig]:
        return self._gconfig

    def get_secondary_guild_id(self, guild_id: int) -> int | None:
        guild = self.cache.get(guild_id)

        if guild is None:
            return None

        return guild.get("secondary_guild_id")

    def get_prefix(self, guild_id: int) -> str:
        return self.cache.get(guild_id, {}).get("prefix") or "."
    
    def get_prefix_member(
        self,
        member_id: int,
        guild_id: int
    ) -> str | None:
        return self.member_cache.get(member_id, {}).get(guild_id)
    
    async def set_prefix_member(
        self,
        member_id: int,
        guild_id: int,
        prefix: str | None
    ) -> None:
        await self.execute(
            """
            INSERT INTO members (member_id, guild_id, prefix)
            VALUES (?, ?, ?)
            ON CONFLICT(member_id, guild_id)
            DO UPDATE SET prefix = excluded.prefix
            """,
            (member_id, guild_id, prefix)
        )

        if prefix is None:
            self.member_cache.get(member_id, {}).pop(guild_id, None)

            if member_id in self.member_cache and not self.member_cache[member_id]:
                del self.member_cache[member_id]

        else:
            self.member_cache.setdefault(member_id, {})[guild_id] = prefix

    def get_channels(self, guild_id: int, channel_name: str) -> list[int]:
        guild_data = self.cache.get(guild_id)
        if not guild_data:
            return []
        return guild_data.get("channels", {}).get(channel_name, [])

    def get_channel(self, guild_id: int, channel_name: str) -> int | None:
        channels = self.get_channels(guild_id, channel_name)
        return channels[0] if channels else None

    def has_permission(
        self, guild_id: int, command: str | None, roles: List[int]
    ) -> bool:
        if command is None:
            return False
        guild_cache = self.cache.get(guild_id)
        if not guild_cache:
            return False
        allowed_roles = guild_cache["permissions"].get(command, [])
        return any(role_id in allowed_roles for role_id in roles)
    
    def get_permission_roles(
        self, guild_id: int, command: str | None
    ) -> List[int]:
        if command is None:
            return []
        guild_cache = self.cache.get(guild_id)
        if not guild_cache:
            return []
        
        allowed_roles = guild_cache["permissions"].get(command, [])
        return allowed_roles

    async def guild_initialize(self, guild_id: int) -> None:
        await self.execute(
            "INSERT OR IGNORE INTO data (guild_id) VALUES (?)", (guild_id,)
        )
        if guild_id not in self.cache:
            self.cache[guild_id] = {
                "channels": {},
                "permissions": {},
                "roles": {},
                "prefix": "",
            }

    def get_ban_limit(self, guild_id: int, role_ids: List[int]) -> int:
        guild = self.cache.get(guild_id)
        if not guild:
            return 0
        role_limits = guild.get("roles", {})
        limits = [role_limits[rid]["limit"] for rid in role_ids if rid in role_limits]
        return max(limits) if limits else 0

    async def is_quarantine_bypassing(self, member_id: int, guild_id: int) -> Tuple:
        row = await self.fetch_one(
            """
            SELECT q.id AS case_id
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
            LIMIT 1;
            """,
            (guild_id, member_id)
        )

        if row is None:
            return (False, None)

        return (True, row["case_id"])

    def ban_queue(self, guild_id: int, role_ids: List[int]) -> bool:
        guild = self.cache.get(guild_id)
        if not guild:
            return False
        role_limits = guild.get("roles", {})
        has_allow = False
        for rid in role_ids:
            perm = role_limits.get(rid, {}).get("ban_queue")
            if perm == 0:
                return False
            if perm == 1:
                has_allow = True
        return has_allow

    def get_role_assignment_scope(self, guild_id: int, role_ids: List[int]) -> str:
        guild_cache = self.cache.get(guild_id)
        if not guild_cache:
            return "none"
        roles_cache = guild_cache.get("roles", {})
        priority = {"none": 0, "specific": 1, "except": 2, "all": 3}
        highest_scope = "none"
        for rid in role_ids:
            role_data = roles_cache.get(rid)
            if not role_data:
                continue
            scope = role_data.get("assignment_scope", "none")
            if priority[scope] > priority[highest_scope]:
                highest_scope = scope
                if highest_scope == "all":
                    return "all"
        return highest_scope

    def get_role_assignment_roles(self, guild_id: int, role_ids: List[int]) -> Set[int]:
        guild_cache = self.cache.get(guild_id)
        if not guild_cache:
            return set()
        roles_cache = guild_cache.get("roles", {})
        result: Set[int] = set()
        for rid in role_ids:
            role_data = roles_cache.get(rid)
            if not role_data:
                continue
            result.update(role_data.get("assignment_roles", set()))
        return result

    def get_role_assignment_rules(self, guild_id: int, author_role_ids: List[int]) -> tuple:
        guild_cache = self.cache.get(guild_id)
        if not guild_cache:
            return False, False, set(), set()
        roles_cache = guild_cache.get("roles", {})

        has_all = False
        has_except_scope = False
        except_ids: Set[int] = set()
        specific_ids: Set[int] = set()

        for rid in author_role_ids:
            role_data = roles_cache.get(rid)
            if not role_data:
                continue
            scope = role_data.get("assignment_scope", "none")
            assignment_roles = role_data.get("assignment_roles", set())

            if scope == "all":
                has_all = True
            elif scope == "specific":
                specific_ids.update(assignment_roles)
            elif scope == "except":
                has_except_scope = True
                except_ids.update(assignment_roles)

        effective_except = except_ids - specific_ids
        return has_all, has_except_scope, effective_except, specific_ids

    def can_assign_role(self, guild_id: int, author_role_ids: List[int], target_role_id: int) -> bool:
        has_all, has_except_scope, effective_except, specific_ids = self.get_role_assignment_rules(guild_id, author_role_ids)

        if has_all:
            return True
        if target_role_id in specific_ids:
            return True
        if target_role_id in effective_except:
            return False
        if has_except_scope:
            return True
        return False

    async def configure_role(
        self,
        guild_id: int,
        role_id: int,
        ban_limit: int,
        ban_queue: int,
        assignment_scope: str,
        roles: Set[int],
        role_type: str,
        role_name: str
    ) -> Dict[str, str | bool]:
        try:
            await self.execute(
                """
                INSERT INTO roles (
                    guild_id, role_id, ban_limit, ban_queue, assignment_scope, role_type, role_name
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, role_id) DO UPDATE SET
                    ban_limit        = excluded.ban_limit,
                    ban_queue        = excluded.ban_queue,
                    assignment_scope = excluded.assignment_scope,
                    role_type = excluded.role_type,
                    role_name = excluded.role_name
                """,
                (guild_id, role_id, ban_limit, ban_queue, assignment_scope, role_type, role_name),
            )

            await self.execute(
                "DELETE FROM role_assignments WHERE guild_id = ? AND role_id = ?",
                (guild_id, role_id),
            )
            for target_role_id in roles:
                await self.execute(
                    """
                    INSERT OR IGNORE INTO role_assignments
                        (guild_id, role_id, target_role_id)
                    VALUES (?, ?, ?)
                    """,
                    (guild_id, role_id, target_role_id),
                )

            guild_cache = self.cache.setdefault(
                guild_id,
                {"channels": {}, "permissions": {}, "roles": {}, "prefix": ""},
            )
            guild_cache["roles"][role_id] = {
                "limit": ban_limit,
                "ban_queue": ban_queue,
                "assignment_scope": assignment_scope,
                "assignment_roles": set(roles),
            }

            return {"success": True, "message": "Successfully configured role!"}

        except Exception as exc:
            return {"success": False, "message": str(exc)}

    async def get_role_configuration(
        self,
        guild_id: int,
        role_id: int,
    ) -> Dict[str, Any]:
        row = await self.fetch_one(
            """
            SELECT
                guild_id,
                role_id,
                ban_limit,
                ban_queue,
                assignment_scope,
                role_type,
                role_name
            FROM roles
            WHERE guild_id = ? AND role_id = ?
            """,
            (guild_id, role_id),
        )

        if row is None:
            return {}

        assignment_rows = await self.fetch_all(
            """
            SELECT target_role_id
            FROM role_assignments
            WHERE guild_id = ? AND role_id = ?
            """,
            (guild_id, role_id),
        )

        return {
            "guild_id": row["guild_id"],
            "role_id": row["role_id"],
            "ban_limit": row["ban_limit"],
            "ban_queue": row["ban_queue"],
            "assignment_scope": row["assignment_scope"],
            "role_type": row["role_type"],
            "role_name": row["role_name"],
            "assignment_roles": {
                assignment["target_role_id"]
                for assignment in assignment_rows
            },
        }

    async def set_prefix(self, guild_id: int, prefix: str) -> None:
        if guild_id not in self.cache:
            self.cache[guild_id] = {
                "channels": {},
                "permissions": {},
                "roles": {},
                "prefix": prefix,
            }
        else:
            self.cache[guild_id]["prefix"] = prefix

        await self.execute(
            """
            INSERT INTO data (guild_id, prefix) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix
            """,
            (guild_id, prefix),
        )

    async def set_channel(
        self, guild_id: int, channel_id: int, channel_type: str
    ) -> None:
        guild = self.cache.setdefault(
            guild_id,
            {"channels": {}, "permissions": {}, "roles": {}, "prefix": "."},
        )
        channel_list = guild["channels"].setdefault(channel_type, [])
        if channel_id not in channel_list:
            channel_list.append(channel_id)

        await self.execute(
            """
            INSERT OR IGNORE INTO guild_channels (guild_id, channel_type, channel_id)
            VALUES (?, ?, ?)
            """,
            (guild_id, channel_type, channel_id),
        )

    async def set_webhook(
        self,
        guild_id: int,
        channel_type: str,
        webhook_url: str
    ) -> None:
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
            """
            SELECT guild_id, webhook_url
            FROM guild_webhooks
            WHERE channel_type = ?
            """,
            (channel_type,),
        )

        return {
            row["guild_id"]: row["webhook_url"]
            for row in rows
        }
    
    async def get_webhook(self, guild_id: int, channel_type: str) -> str | None:
        row = await self.fetch_one(
            """
            SELECT webhook_url
            FROM guild_webhooks
            WHERE guild_id = ?
            AND channel_type = ?
            LIMIT 1
            """,
            (guild_id, channel_type),
        )

        return row["webhook_url"] if row else None

    async def set_permission(self, guild_id: int, role_id: int, command: str) -> None:
        guild = self.cache.setdefault(
            guild_id,
            {"channels": {}, "permissions": {}, "roles": {}, "prefix": "."},
        )
        role_list = guild["permissions"].setdefault(command, [])
        if role_id not in role_list:
            role_list.append(role_id)

        await self.execute(
            """
            INSERT OR IGNORE INTO permissions (guild_id, role_id, command)
            VALUES (?, ?, ?)
            """,
            (guild_id, role_id, command),
        )

    def get_permissions(self, guild_id: int, role_id: int) -> list[str]:
        guild = self.cache.get(guild_id)

        if guild is None:
            return []

        permissions = guild.get("permissions", {})

        return [
            command
            for command, role_ids in permissions.items()
            if role_id in role_ids
        ]

    async def remove_channel(
        self,
        guild_id: int,
        channel_id: Optional[int] = None,
        channel_type: Optional[str] = None,
    ) -> None:
        if channel_id is None and channel_type is None:
            raise ValueError("remove_channel requires at least one of channel_id or channel_type")

        guild = self.cache.get(guild_id)
        if guild:
            channels = guild.get("channels", {})

            if channel_type and channel_id:
                if channel_type in channels:
                    channels[channel_type] = [
                        c for c in channels[channel_type] if c != channel_id
                    ]
                    if not channels[channel_type]:
                        del channels[channel_type]

            elif channel_id:
                for ctype in list(channels.keys()):
                    channels[ctype] = [c for c in channels[ctype] if c != channel_id]
                    if not channels[ctype]:
                        del channels[ctype]

            elif channel_type:
                channels.pop(channel_type, None)

        if channel_type and channel_id:
            await self.execute(
                """
                DELETE FROM guild_channels
                WHERE guild_id = ? AND channel_id = ? AND channel_type = ?
                """,
                (guild_id, channel_id, channel_type),
            )
        elif channel_id:
            await self.execute(
                "DELETE FROM guild_channels WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            )
        elif channel_type:
            await self.execute(
                "DELETE FROM guild_channels WHERE guild_id = ? AND channel_type = ?",
                (guild_id, channel_type),
            )

    async def remove_permission(
        self,
        guild_id: int,
        role_id: int,
        command: Optional[str] = None,
    ) -> None:
        guild = self.cache.get(guild_id)
        if guild:
            permissions = guild.get("permissions", {})
            if command:
                if command in permissions and role_id in permissions[command]:
                    permissions[command].remove(role_id)
                    if not permissions[command]:
                        del permissions[command]
            else:
                for cmd in list(permissions.keys()):
                    if role_id in permissions[cmd]:
                        permissions[cmd].remove(role_id)
                    if not permissions[cmd]:
                        del permissions[cmd]

        if command:
            await self.execute(
                """
                DELETE FROM permissions
                WHERE guild_id = ? AND role_id = ? AND command = ?
                """,
                (guild_id, role_id, command),
            )
        else:
            await self.execute(
                "DELETE FROM permissions WHERE guild_id = ? AND role_id = ?",
                (guild_id, role_id),
            )

    async def save_ticket_view(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        config: dict,
    ) -> None:
        await self.execute(
            """
            INSERT OR REPLACE INTO ticket_views
                (guild_id, channel_id, message_id, config_json)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, channel_id, message_id, json.dumps(config)),
        )

    async def get_ticket_views(self, guild_id: Optional[int] = None) -> list:
        if guild_id:
            return await self.fetch_all(
                """
                SELECT guild_id, channel_id, message_id, config_json
                FROM ticket_views
                WHERE guild_id = ?
                """,
                (guild_id,),
            )
        return await self.fetch_all(
            "SELECT guild_id, channel_id, message_id, config_json FROM ticket_views"
        )

    async def delete_ticket_view(self, message_id: int) -> None:
        await self.execute(
            "DELETE FROM ticket_views WHERE message_id = ?", (message_id,)
        )

    async def write_log(self, guild_id: int, user_id: int, log_txt: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.execute(
            """
            INSERT INTO botlogs (guild_id, member_id, timestamp, log)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, user_id, timestamp, log_txt),
        )

    async def log_moderation_action(
        self,
        guild_id: int,
        moderator_id: int,
        target_user_id: int,
        mod_type: str,
        reason: str = "No reason provided",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        metadata = metadata or {}

        timestamp = datetime.now(pytz.utc).isoformat()

        await self.ensure_staff(moderator_id, guild_id)
        await self.ensure_member(target_user_id, guild_id)

        _guild_id = self.get_secondary_guild_id(guild_id) or guild_id

        row_id = await self.execute(
            """
            INSERT INTO modlogs
                (
                    guild_id,
                    moderator_id,
                    target_user_id,
                    mod_type,
                    reason,
                    timestamp,
                    metadata
                )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _guild_id,
                moderator_id,
                target_user_id,
                mod_type.lower(),
                reason,
                timestamp,
                json.dumps(metadata),
            ),
        )

        return row_id

    async def log_proof_action(
        self,
        guild_id: int,
        case_id: int,
        proof_reference: int,
        author: int,
    ) -> None:
        await self.ensure_staff(author, guild_id)
        await self.execute(
            """
            INSERT INTO proofs (guild_id, case_id, proof_reference, author)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, case_id, proof_reference, author),
        )

    async def get_proof_references(
        self,
        guild_id: int,
        case_id: int,
    ) -> List[int]:
        rows = await self.fetch_all(
            """
            SELECT proof_reference
            FROM proofs
            WHERE guild_id = ? AND case_id = ?
            ORDER BY id ASC
            """,
            (guild_id, case_id),
        )

        return [row["proof_reference"] for row in rows]

    async def retrieve_proofs(self, case_id: int) -> list[int]:
        rows = await self.fetch_all(
            "SELECT proof_reference FROM proofs WHERE case_id = ?", (case_id,)
        )
        return [row["proof_reference"] for row in rows]

    async def get_ban_limit_status(
        self,
        guild_id: int,
        moderator_id: int,
        moderator_role_ids: list[int],
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

        now = datetime.now(pytz.utc)
        past_24h = (now - timedelta(hours=24)).isoformat()

        try:
            max_limit = self.get_ban_limit(guild_id, moderator_role_ids)
            if max_limit == 0:
                return _default

            bans = await self.fetch_all(
                """
                SELECT timestamp
                FROM  modlogs
                WHERE  guild_id = ? 
                AND deleted = 0
                AND moderator_id  = ?
                AND mod_type IN ('ban', 'quarantine')
                AND timestamp     >= ?
                ORDER BY timestamp ASC
                """,
                (guild_id, moderator_id, past_24h),
            )

            recent_ban_count = len(bans)
            exceeded = recent_ban_count >= max_limit
            remaining_count = max(0, max_limit - recent_ban_count)
            remaining_time: Optional[str] = None
            cooldown_breakdown: Optional[str] = None

            if exceeded and bans:
                oldest_ts = datetime.fromisoformat(bans[0]["timestamp"])
                cooldown_end = oldest_ts + timedelta(hours=24)

                if cooldown_end > now:
                    remaining = cooldown_end - now
                    hours, rem = divmod(int(remaining.total_seconds()), 3600)
                    minutes = rem // 60
                    remaining_time = f"You can ban again in {hours}h {minutes}m"

                lines = []
                for index, row in enumerate(bans, start=1):
                    ban_time = datetime.fromisoformat(row["timestamp"])
                    ban_cooldown_end = ban_time + timedelta(hours=24)
                    if ban_cooldown_end > now:
                        remaining = ban_cooldown_end - now
                        hours, rem = divmod(int(remaining.total_seconds()), 3600)
                        minutes = rem // 60
                        lines.append(f"{index}. Recovery in **{hours}h {minutes}m**")

                if lines:
                    cooldown_breakdown = "**Ban's Cooldown State.**\n" + "\n".join(
                        lines
                    )

            return BanLimitStatus(
                exceeded=exceeded,
                max_limit=max_limit,
                recent_ban_count=recent_ban_count,
                remaining_count=remaining_count,
                remaining_time=remaining_time,
                cooldown_breakdown=cooldown_breakdown,
            )

        except Exception as exc:
            print("Error in get_ban_limit_status:", exc)
            return _default

    async def fetch_mod_stats(
        self,
        guild_id: int,
        moderator_id: int,
        page_start: int,
        page_end: int,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        start_today = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        start_week = (
            (now - timedelta(days=now.weekday()))
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .isoformat()
        )
        start_month = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        stats_rows = await self.fetch_all(
            """
            SELECT
                mod_type,
                COUNT(*) AS total,
                COUNT(CASE WHEN timestamp >= ? THEN 1 END) AS today,
                COUNT(CASE WHEN timestamp >= ? THEN 1 END) AS week,
                COUNT(CASE WHEN timestamp >= ? THEN 1 END) AS month
            FROM modlogs
            WHERE 
                guild_id = ? AND 
                moderator_id = ? AND 
                deleted = 0 AND
                LOWER(mod_type) NOT IN ('unban', 'unmute', 'quarantine_release')
            GROUP BY mod_type
            """,
            (start_today, start_week, start_month, guild_id, moderator_id),
        )

        if not stats_rows:
            return {
                "success": False,
                "message": "No Logs Found",
                "logs": [],
                "stats": {},
            }

        page_rows = await self.fetch_all(
            """
            SELECT
                target_user_id,
                mod_type,
                reason,
                CAST(strftime('%s', timestamp) AS INTEGER) AS timestamp
            FROM modlogs
            WHERE 
                guild_id = ? AND 
                moderator_id = ? AND
                deleted = 0 AND
                LOWER(mod_type) NOT IN ('unban', 'unmute', 'quarantine_release')
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            (guild_id, moderator_id, page_end - page_start, page_start),
        )

        total_logs = sum(row["total"] for row in stats_rows)

        stats = {
            row["mod_type"].lower(): {
                "today": row["today"],
                "7d": row["week"],
                "30d": row["month"],
                "total": row["total"],
            }
            for row in stats_rows
        }
        stats = defaultdict(lambda: {"today": 0, "7d": 0, "30d": 0, "total": 0}, stats)

        logs = [
            {
                "target_user_id": row["target_user_id"],
                "mod_type": row["mod_type"].lower(),
                "reason": row["reason"],
                "timestamp": row["timestamp"],
            }
            for row in page_rows
        ]

        return {
            "success": True,
            "logs": logs,
            "total_logs": total_logs,
            "stats": stats,
            "now": now,
        }

    async def fetch_mod_logs(
        self,
        guild_id: int,
        target_user_id: int,
        *,
        moderator_id: int | None = None,
        mod_type: str = "all",
        page: int = 1,
        page_size: int = 3,
    ) -> Dict[str, Any]:
        """If there is a secondary guild id then we should fetch modlogs of that guild id instead"""
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1:
            raise ValueError("page_size must be >= 1")

        _guild_id = self.get_secondary_guild_id(guild_id) or guild_id

        conditions = ["guild_id = ?", "target_user_id = ?", "deleted = 0"]
        params: list[Any] = [_guild_id, target_user_id]

        if moderator_id is not None:
            conditions.append("moderator_id = ?")
            params.append(moderator_id)

        normalized_type = mod_type.lower()
        if normalized_type != "all":
            conditions.append("lower(mod_type) = ?")
            params.append(normalized_type)

        where_clause = " AND ".join(conditions)

        count_row = await self.fetch_one(
            f"SELECT COUNT(*) AS total FROM modlogs WHERE {where_clause}",
            tuple(params),
        )
        total_count = count_row["total"] if count_row is not None else 0

        if not total_count:
            return {
                "success": False,
                "message": "No logs found",
                "results": [],
                "page": page,
                "has_prev": False,
                "has_next": False,
                "total_count": 0,
                "max_page": 1,
            }

        max_page = max(1, -(-total_count // page_size))
        offset = (page - 1) * page_size

        query = f"""
            SELECT id, moderator_id, mod_type, reason, timestamp
            FROM modlogs
            WHERE {where_clause}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """
        rows = await self.fetch_all(query, tuple(params) + (page_size + 1, offset))

        has_next = len(rows) > page_size
        rows = rows[:page_size]

        return {
            "success": True,
            "results": [
                {
                    "case_id": row["id"],
                    "moderator_id": row["moderator_id"],
                    "mod_type": row["mod_type"].lower(),
                    "reason": row["reason"],
                    "timestamp": row["timestamp"],
                }
                for row in rows
            ],
            "page": page,
            "has_prev": page > 1,
            "has_next": has_next,
            "total_count": total_count,
            "max_page": max_page,
        }

    async def fetch_moderation_leaderboard(
        self, guild_id: int, lb_type: str = "total"
    ) -> Dict:
        valid_types = {"total", "daily", "weekly", "monthly"}
        if lb_type not in valid_types:
            lb_type = "total"

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
                        >= datetime('now','weekday 1','start of day','-7 days')
                    THEN 1 END) AS weekly,
                COUNT(CASE
                    WHEN datetime(replace(substr(m.timestamp,1,19),'T',' '))
                        >= datetime('now','start of month')
                    THEN 1 END) AS monthly
            FROM modlogs m
            JOIN staffs s
                ON s.staff_id = m.moderator_id
            AND s.guild_id = m.guild_id
            WHERE 
                m.guild_id = ?
                AND m.deleted = 0
                AND s.on_loa = 0
                AND s.retired = 0
                AND LOWER(m.mod_type) NOT IN ('unban', 'unmute', 'quarantine_release')
            GROUP BY m.moderator_id
            ORDER BY {lb_type} DESC;
            """,
            (guild_id,),
        )

        leaderboard = []
        for row in rows:
            value = row[lb_type]
            leaderboard.append({"moderator_id": row["moderator_id"], "ms": value})

        return {"moderator_statistics_leaderboard": leaderboard}

    async def case_exists(self, case_id: int, guild_id: int) -> bool:
        row = await self.fetch_one(
            "SELECT moderator_id FROM modlogs WHERE id = ? AND guild_id = ? AND deleted = 0",
            (case_id, guild_id),
        )
        return row is not None

    async def edit_case(
        self,
        staff_id: int,
        case_id: int,
        case_statement: str,
        absolute: bool,
    ) -> Dict[str, Any]:
        try:
            row = await self.fetch_one(
                "SELECT moderator_id FROM modlogs WHERE id = ? AND deleted = 0", (case_id,)
            )
            if row is None:
                return {"success": False, "message": "Case not found."}

            if row["moderator_id"] != staff_id and not absolute:
                return {
                    "success": False,
                    "message": (
                        f"This case cannot be modified. "
                        f"Only <@{row['moderator_id']}> can modify it."
                    ),
                }

            await self.execute(
                "UPDATE modlogs SET reason = ? WHERE id = ?",
                (case_statement, case_id),
            )
            return {"success": True, "message": "Case edited successfully."}

        except Exception as exc:
            return {"success": False, "message": f"An error occurred: {exc}"}

    async def get_case(
        self,
        case_id: int,
    ) -> Optional[Dict[str, Any]]:
        row = await self.fetch_one(
            """
            SELECT
                *
            FROM modlogs
            WHERE id = ?
            """,
            (case_id,),
        )

        if row is None:
            return None

        return dict(row)

    async def delete_case(self, case_id: int) -> Dict[str, Any]:
        if not case_id:
            return {
                "success": False,
                "message": "Invalid case_id provided.",
                "case_id": case_id,
            }
        try:
            await self.execute("UPDATE modlogs SET deleted = 1 WHERE id = ?", (case_id,))
            return {
                "success": True,
                "message": "Case deleted successfully.",
                "case_id": case_id,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to delete case: {e}",
                "case_id": case_id,
            }

    async def get_ticket_by_id(self, ticket_id: int) -> Optional[Tuple]:
        row = await self.fetch_one(
            """
            SELECT opened_user_id, ticket_type, log_channel_id,
                   submission_json, claimer_user_id
            FROM tickets
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        )
        return tuple(row) if row else None

    async def get_ticket_by_opener(self, opener_id: int, guild_id: int) -> List[Tuple]:
        rows = await self.fetch_all(
            """
            SELECT ticket_id FROM tickets
            WHERE opened_user_id = ? AND guild_id = ?
            """,
            (opener_id, guild_id),
        )
        return [tuple(row) for row in rows]

    async def get_ticket_owner(self, ticket_id: int) -> Optional[int]:
        row = await self.fetch_one(
            "SELECT opened_user_id FROM tickets WHERE ticket_id = ?",
            (ticket_id,),
        )
        return row["opened_user_id"] if row else None

    async def get_guild_tickets(self, guild_id: int) -> List[Tuple]:
        rows = await self.fetch_all(
            """
            SELECT ticket_id, opened_user_id, submission_json, message_id, ticket_details_message_id
            FROM tickets WHERE guild_id = ?
            """,
            (guild_id,),
        )
        return [tuple(row) for row in rows]

    async def get_ticket_claimer(self, ticket_id: int) -> int | None:
        row = await self.fetch_one(
            "SELECT claimer_user_id FROM tickets WHERE ticket_id = ?",
            (ticket_id,),
        )
        return row["claimer_user_id"] if row else None

    async def reset_ticket_claimer(self, ticket_id: int) -> None:
        await self.execute(
            "UPDATE tickets SET claimer_user_id = NULL WHERE ticket_id = ?",
            (ticket_id,),
        )

    async def set_ticket_claimer(
        self,
        claimer: int,
        ticket_id: int,
        guild_id: int
    ) -> bool:
        
        """ Let's ensure the member """
        await self.ensure_member(claimer, guild_id)


        updated = await self.execute(
            """
            UPDATE tickets
            SET claimer_user_id = ?
            WHERE ticket_id = ?
            AND claimer_user_id IS NULL
            """,
            (claimer, ticket_id),
            row_count=True
        )

        return updated == 1

    async def create_ticket_log(
        self,
        guild_id: int,
        opened_user_id: int,
        staff_handled: int | None,
        reason: str | None,
        ticket_type: str,
        transcripts_reference: int | None,
        transcript_channel: int
    ) -> int | None:
        
        """ Let's just prefer supplementary guild for now """
        _guild_id = self.get_secondary_guild_id(guild_id) or guild_id


        await self.ensure_member(opened_user_id, _guild_id)
        if staff_handled:
            await self.ensure_staff(staff_handled, _guild_id)

        row_id = await self.execute(
            """
            INSERT INTO ticket_logs (
                guild_id, opened_user_id, staff_handled, reason,
                ticket_type, timestamp, transcripts_reference, logs_channel_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _guild_id,
                opened_user_id,
                staff_handled,
                reason,
                ticket_type,
                datetime.now(UTC).isoformat(),
                transcripts_reference,
                transcript_channel
            ),
        )
        return row_id

    async def get_ticket_log(self, id: int, guild_id: int) -> dict[str, Any] | None:
        row = await self.fetch_one(
            """
            SELECT *
            FROM ticket_logs
            WHERE id = ? AND guild_id = ?
            """,
            (id, guild_id),
        )
        if row is None:
            return None
        return dict(row)

    async def get_ticket_logs(
        self,
        guild_id: int,
        *,
        opened_user_id: int | None = None,
        staff_handled: int | None = None,
        ticket_type: str | None = None,
        page: int = 1,
        page_size: int = 3,
    ) -> dict[str, Any]:
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1:
            raise ValueError("page_size must be >= 1")

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
            f"SELECT COUNT(*) AS total FROM ticket_logs WHERE {where_clause}",
            tuple(params),
        )
        total_count = count_row["total"] if count_row is not None else 0
        max_page = max(1, -(-total_count // page_size))  # ceil division

        offset = (page - 1) * page_size

        query = f"""
            SELECT id, opened_user_id, staff_handled, ticket_type, timestamp
            FROM ticket_logs
            WHERE {where_clause}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """
        rows = await self.fetch_all(query, tuple(params) + (page_size + 1, offset))

        has_next = len(rows) > page_size
        rows = rows[:page_size]

        return {
            "results": [
                {
                    "id": row["id"],
                    "opened_user_id": row["opened_user_id"],
                    "staff_handled": row["staff_handled"],
                    "ticket_type": row["ticket_type"],
                    "timestamp": row["timestamp"],
                }
                for row in rows
            ],
            "page": page,
            "has_prev": page > 1,
            "has_next": has_next,
            "total_count": total_count,
            "max_page": max_page,
        }

    async def get_ticket_types(self, guild_id: int) -> List[str]:
        rows = await self.fetch_all(
            """
            SELECT DISTINCT ticket_type
            FROM ticket_logs
            WHERE guild_id = ?
            AND ticket_type IS NOT NULL
            """,
            (guild_id,),
        )

        return [row["ticket_type"] for row in rows]

    async def delete_ticket(self, ticket_id: int) -> None:
        await self.execute("DELETE FROM tickets WHERE ticket_id = ?", (ticket_id,))

    async def create_ticket(
        self,
        ticket_id: int,
        guild_id: int,
        opened_user_id: int,
        ticket_type: str,
        log_channel_id: int,
        submission_json: dict,
        message_id: Optional[int] = None,
        ticket_details_message_id: Optional[int] = None
    ) -> None:
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
                ticket_id,
                guild_id,
                opened_user_id,
                ticket_type,
                log_channel_id,
                json.dumps(submission_json),
                message_id,
                ticket_details_message_id
            ),
        )

    async def update_ticket_message_id(self, ticket_id: int, message_id: int) -> None:
        await self.execute(
            "UPDATE tickets SET message_id = ? WHERE ticket_id = ?",
            (message_id, ticket_id),
        )

    async def update_ticket_submission(
        self, ticket_id: int, submission_json: dict
    ) -> None:
        await self.execute(
            "UPDATE tickets SET submission_json = ? WHERE ticket_id = ?",
            (json.dumps(submission_json), ticket_id),
        )

    async def ensure_member(self, member_id: int, guild_id: int) -> None:
        await self.execute(
            "INSERT OR IGNORE INTO members (member_id, guild_id) VALUES (?, ?)",
            (member_id, guild_id),
        )

    async def ensure_staff(self, staff_id: int, guild_id: int) -> None:
        await self.execute(
            """
            INSERT OR IGNORE INTO staffs (staff_id, guild_id, name)
            VALUES (?, ?, 'Unknown')
            """,
            (staff_id, guild_id),
        )

    async def fetch_staff_detail(self, staff_id: int, guild_id: int) -> Dict[str, Any]:
        query = """
        SELECT
            s.name,
            GROUP_CONCAT(DISTINCT r.role_name) AS roles,
            s.on_loa,
            COALESCE(sc.strikes_count, 0) AS strikes_count,
            s.joined_on,
            m.timezone,
            s.responsibility,
            s.retired,
            MAX(m.avatar_url) AS avatar_url
        FROM staffs s
        LEFT JOIN staff_roles sr
            ON s.staff_id = sr.staff_id 
            AND s.guild_id = sr.guild_id
        LEFT JOIN roles r
            ON sr.role_id = r.role_id 
            AND sr.guild_id = r.guild_id
        LEFT JOIN (
            SELECT guild_id, issued_to_id, COUNT(*) AS strikes_count
            FROM strikes
            GROUP BY guild_id, issued_to_id
        ) sc
            ON sc.guild_id = s.guild_id 
            AND sc.issued_to_id = s.staff_id
        LEFT JOIN members m
            ON m.member_id = s.staff_id 
            AND m.guild_id = s.guild_id
        WHERE s.staff_id = ? 
        AND s.guild_id = ?
        GROUP BY
            s.staff_id,
            s.guild_id,
            s.name,
            s.on_loa,
            s.joined_on,
            m.timezone,
            s.responsibility,
            s.retired,
            sc.strikes_count;
        """
        row = await self.fetch_one(query, (staff_id, guild_id))
        if not row:
            return {}

        name = row["name"]
        role_names = row["roles"]
        is_loa = row["on_loa"]
        strikes_count = row["strikes_count"]
        joined_on_str = row["joined_on"]
        tz_str = row["timezone"]
        responsibility = row["responsibility"]
        retired = row["retired"]
        avatar_url = row["avatar_url"]

        roles_list = role_names.split(",") if role_names else []

        if joined_on_str:
            joined_on = datetime.strptime(joined_on_str, "%d/%m/%Y")
            joined_on_timestamp = int(joined_on.timestamp())
        else:
            joined_on_timestamp = int(datetime.now(timezone.utc).timestamp())

        return {
            "name": name,
            "avatar_url": avatar_url,
            "role_name": roles_list,
            "is_loa": is_loa,
            "strikes_count": strikes_count,
            "joined_on": joined_on_timestamp,
            "timezone": tz_str,
            "responsibility": responsibility,
            "retired": retired,
        }

    async def fetch_all_staffs(self, guild_id: int) -> Dict[str, Any]:
        count_rows = await self.fetch_all(
            """
            SELECT
                r.role_type,
                srk.role_id,
                srk.priority,
                COUNT(
                    DISTINCT CASE
                        WHEN s.retired = 0
                        THEN s.staff_id
                    END
                ) AS total_staffs,
                COUNT(
                    DISTINCT CASE
                        WHEN s.on_loa = 1
                        AND s.retired = 0
                        THEN s.staff_id
                    END
                ) AS loa_staffs,
                COUNT(
                    DISTINCT CASE
                        WHEN s.on_loa = 0
                        AND s.retired = 0
                        THEN s.staff_id
                    END
                ) AS active_staffs
            FROM staff_ranks srk
            JOIN roles r
                ON r.guild_id = srk.guild_id
            AND r.role_id = srk.role_id
            LEFT JOIN staff_roles sr
                ON sr.guild_id = srk.guild_id
            AND sr.role_id = srk.role_id
            LEFT JOIN staffs s
                ON s.guild_id = sr.guild_id
            AND s.staff_id = sr.staff_id
            WHERE srk.guild_id = ?
            GROUP BY
                srk.role_id,
                srk.priority,
                r.role_type
            ORDER BY
                srk.priority ASC;
            """,
            (guild_id,),
        )

        role_count_result: Dict[str, Any] = {}
        for row in count_rows:
            role = role_count_result.setdefault(
                row["role_type"],
                {
                    "total": 0,
                    "loa": 0,
                    "active": 0,
                },
            )

            role["total"] += row["total_staffs"]
            role["loa"] += row["loa_staffs"]
            role["active"] += row["active_staffs"]

        rows = await self.fetch_all(
            """
            SELECT
                srk.priority,
                r.role_id,
                r.role_name,
                r.role_type,
                s.staff_id,
                s.name,
                s.joined_on,
                s.on_loa,
                m.avatar_url,
                m.timezone
            FROM staff_ranks srk
            JOIN roles r
                ON r.guild_id = srk.guild_id
            AND r.role_id = srk.role_id
            LEFT JOIN staff_roles sr
                ON sr.guild_id = srk.guild_id
            AND sr.role_id = srk.role_id
            LEFT JOIN staffs s
                ON s.guild_id = sr.guild_id
            AND s.staff_id = sr.staff_id
            AND s.retired = 0
            LEFT JOIN members m
                ON m.guild_id = s.guild_id
            AND m.member_id = s.staff_id
            WHERE srk.guild_id = ?
            ORDER BY
                srk.priority,
                s.name;
            """,
            (guild_id,),
        )

        role_user_map: Dict[Any, Any] = {}
        time_now = datetime.now(timezone.utc)

        for row in rows:
            role_id = row["role_id"]
            role_name = row["role_name"]
            staff_id = row["staff_id"]
            name = row["name"]
            avatar_url = row["avatar_url"] or "https://cdn3.emoji.gg/emojis/928205-membericon.png"
            joined_on = row["joined_on"]
            tz_str = row["timezone"]
            role_type = row["role_type"]

            try:
                dt = (
                    datetime.strptime(joined_on, "%d/%m/%Y").replace(
                        tzinfo=timezone.utc
                    )
                    if joined_on
                    else time_now
                )
            except ValueError:
                dt = time_now

            unix_timestamp = int(dt.timestamp())

            role = role_user_map.setdefault(
                role_id,
                {
                    "role_name": role_name,
                    "role_type": role_type,
                    "priority": row["priority"],
                    "staff": [],
                },
            )

            if staff_id is not None:
                role["staff"].append(
                    {
                        "name": name,
                        "id": staff_id,
                        "avatar_profile": avatar_url,
                        "joined_on": unix_timestamp,
                        "timezone": tz_str or "Default",
                    }
                )

        return {"overall": role_count_result, "roles": role_user_map}

    async def assert_staff_role_permission(
        self,
        staff_id: int,
        updated_by: int,
        guild_id: int,
    ) -> bool:
        """Returns True if the updater's role hierarchy priority is higher than the target user's role hierarchy priority."""
        current_role_row = await self.fetch_one(
            """
            SELECT sr.role_id, srk.priority
            FROM staff_roles sr
            JOIN roles r
                ON sr.role_id = r.role_id
                AND sr.guild_id = r.guild_id
            LEFT JOIN staff_ranks srk
                ON srk.role_id = r.role_id
                AND srk.guild_id = r.guild_id
            WHERE sr.staff_id = ?
                AND sr.guild_id = ?
                AND r.role_type = 'staff'
            ORDER BY srk.priority ASC
            LIMIT 1;
            """,
            (staff_id, guild_id),
        )

        if not current_role_row:
            return False

        updater_row = await self.fetch_one(
            """
            SELECT srk.priority
            FROM staff_roles sr
            JOIN roles r
                ON sr.role_id = r.role_id
                AND sr.guild_id = r.guild_id
            JOIN staff_ranks srk
                ON srk.role_id = r.role_id
                AND srk.guild_id = r.guild_id
            WHERE sr.staff_id = ?
                AND sr.guild_id = ?
                AND r.role_type = 'staff'
            ORDER BY srk.priority ASC
            LIMIT 1;
            """,
            (updated_by, guild_id),
        )

        if not updater_row:
            return False

        return current_role_row["priority"] >= updater_row["priority"]

    async def add_staff(
        self, staff_id: int, guild_id: int, name: str, avatar_url: str
    ) -> Dict[str, Any]:
        row = await self.fetch_one(
            "SELECT retired FROM staffs WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        )

        if row:
            await self.ensure_member(staff_id, guild_id)
            if row["retired"] == 1:
                await self.execute(
                    """
                    UPDATE staffs
                    SET retired = 0, name = ?, avatar_url = ?
                    WHERE staff_id = ? AND guild_id = ?
                    """,
                    (name, avatar_url, staff_id, guild_id),
                    commit=True,
                )
            else:
                return {"success": False, "message": "Staff entry already exists"}
        else:
            today = datetime.now().strftime("%d/%m/%Y")
            await self.execute(
                """
                INSERT INTO staffs (
                    staff_id, name, guild_id, on_loa, retired,
                    responsibility, avatar_url, joined_on
                )
                VALUES (?, ?, ?, 0, 0, 'None', ?, ?)
                """,
                (staff_id, name, guild_id, avatar_url, today),
                commit=True,
            )

        base_roles: list[int] = []
        try:
            configs = await self.fetch_all(
                "SELECT role_id FROM roles WHERE guild_id = ? AND role_type = 'staff_base'",
                (guild_id,),
            )

            base_roles = [row["role_id"] for row in configs]
        except Exception:
            pass  # staff_configs may not exist in all deployments

        initial_role_row = await self.fetch_one(
            """
            SELECT r.role_id
            FROM roles r
            JOIN staff_ranks srk
                ON  srk.guild_id = r.guild_id
                AND srk.role_id  = r.role_id
            WHERE r.guild_id  = ?
            AND   r.role_type = 'staff'
            ORDER BY srk.priority DESC
            LIMIT 1
            """,
            (guild_id,),
        )
        initial_role: Optional[int] = (
            initial_role_row["role_id"] if initial_role_row else None
        )

        if initial_role:

            await self.execute(
                """
                INSERT OR IGNORE INTO staff_roles (staff_id, guild_id, role_id)
                VALUES (?, ?, ?)
                """,
                (staff_id, guild_id, initial_role),
                commit=True,
            )

        roles_to_add = set(base_roles)
        if initial_role:
            roles_to_add.add(initial_role)

        return {
            "success": True,
            "roles_to_add": list(roles_to_add),
            "message": "Staff added successfully",
        }

    async def remove_staff(self, staff_id: int, guild_id: int) -> Dict[str, Any]:
        row = await self.fetch_one(
            "SELECT retired FROM staffs WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        )
        if not row:
            return {"success": False, "message": "Staff not found"}
        if row["retired"] == 1:
            return {"success": False, "message": "Staff is already retired"}

        await self.execute(
            "UPDATE staffs SET retired = 1 WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
            commit=True,
        )

        role_rows = await self.fetch_all(
            "SELECT role_id FROM staff_roles WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        )
        role_ids = [r["role_id"] for r in role_rows]

        base_roles: list[int] = []
        try:
            configs = await self.fetch_all(
                "SELECT role_id FROM roles WHERE guild_id = ? AND role_type = 'staff_base'",
                (guild_id,),
            )

            base_roles = [row["role_id"] for row in configs]
        except Exception:
            pass

        await self.execute(
            "DELETE FROM staff_roles WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
            commit=True,
        )

        return {
            "success": True,
            "message": "Staff marked as retired",
            "roles_to_remove": list(set(role_ids + base_roles)),
        }

    async def edit_staff(
        self,
        staff_id: int,
        guild_id: int,
        name: Optional[str],
        joined_on: Optional[str],
        timezone: Optional[str],
        responsibility: Optional[str],
    ) -> Dict[str, Any]:

        await self.ensure_member(staff_id, guild_id)

        if not await self.fetch_one(
            "SELECT 1 FROM staffs WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        ):
            return {
                "success": False,
                "message": f"No staff found with ID {staff_id}",
            }

        if any([name, joined_on, responsibility]):
            fields = {
                "name": name,
                "joined_on": joined_on,
                "responsibility": responsibility,
            }

            fields = {k: v for k, v in fields.items() if v is not None}

            await self.execute(
                f"""
                UPDATE staffs
                SET {", ".join(f"{k} = ?" for k in fields)}
                WHERE staff_id = ? AND guild_id = ?
                """,
                (*fields.values(), staff_id, guild_id),
            )

        if timezone:
            await self.execute(
                """
                UPDATE members
                SET timezone = ?
                WHERE member_id = ? AND guild_id = ?
                """,
                (timezone, staff_id, guild_id),
            )

        if not any([name, joined_on, responsibility, timezone]):
            return {
                "success": False,
                "message": "No fields provided to update",
            }

        return {
            "success": True,
            "message": f"Staff ID {staff_id} updated successfully",
        }

    async def strike_staff(
        self,
        staff_id: int,
        guild_id: int,
        issued_by: int,
        reason: str,
        type: str,
        expiry_date: str
    ) -> Dict[str, Any]:
        await self.ensure_staff(issued_by, guild_id)
        await self.ensure_staff(staff_id, guild_id)

        has_permission: bool = await self.assert_staff_role_permission(staff_id, issued_by, guild_id)
        if not has_permission:
            return {"success": False, "message": f"Action has been denied due to <@{staff_id}> having higher rank than you"}


        if expiry_date == "none":
            iso_string = None
        else:
            days = int(expiry_date[:-1])
            expires_on = datetime.now(UTC) + timedelta(days=days)
            iso_string = expires_on.isoformat()

        await self.execute(
            """
            INSERT INTO strikes (issued_by_id, issued_to_id, reason, date, guild_id, type, expiry_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issued_by,
                staff_id,
                reason,
                datetime.now(UTC).isoformat(),
                guild_id,
                type,
                iso_string
            ),
        )
        return {
            "success": True,
            "staff_id": staff_id,
            "issued_by": issued_by,
            "reason": reason,
            "message": f"Successfully issued a {type} infraction to staff <@{staff_id}>",
        }

    async def remove_strike(
        self, strike_id: int, guild_id: int
    ) -> Dict[str, str | bool | int]:
        row = await self.fetch_one(
            """
            SELECT issued_to_id ,issued_by_id, reason FROM strikes
            WHERE strike_id = ? AND guild_id = ?
            """,
            (strike_id, guild_id),
        )
        if not row:
            return {
                "success": False,
                "message": f"No strike with ID `{strike_id}` found",
            }

        staff_id = row["issued_to_id"]
        await self.execute("DELETE FROM strikes WHERE strike_id = ?", (strike_id,))
        return {
            "success": True,
            "message": f"Strike `{strike_id}` removed from <@{staff_id}>",
            "issued_to": row["issued_to_id"],
            "issued_by": row["issued_by_id"],
            "reason": row["reason"]
        }

    async def edit_strike(
        self,
        strike_id: int,
        guild_id: int,
        staff_id: int,
        new_reason: str,
    ) -> Dict[str, str | bool]:
        row = await self.fetch_one(
            """
            SELECT issued_to_id, issued_by_id FROM strikes
            WHERE strike_id = ? AND guild_id = ?
            """,
            (strike_id, guild_id),
        )
        if not row:
            return {
                "success": False,
                "message": f"No strike with ID `{strike_id}` found",
            }

        if row["issued_by_id"] != staff_id:
            return {
                "success": False,
                "message": "Only the staff who issued the strike can edit it.",
            }

        await self.execute(
            "UPDATE strikes SET reason = ? WHERE strike_id = ? AND guild_id = ?",
            (new_reason, strike_id, guild_id),
        )
        return {
            "success": True,
            "message": f"Strike `{strike_id}` edited successfully!",
        }

    async def get_strike(
        self,
        strike_id: int,
        guild_id: int
    ) -> Dict[str, Any]:
        row = await self.fetch_one(
            "SELECT * FROM strikes WHERE strike_id = ? AND guild_id = ?",
            (strike_id, guild_id)
        )

        return dict(row)

    async def fetch_staff_strikes(
        self,
        staff_id: int,
        guild_id: int,
        *,
        page: int = 1,
        page_size: int = 3,
    ) -> Dict[str, Any]:
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1:
            raise ValueError("page_size must be >= 1")

        conditions = ["issued_to_id = ?", "guild_id = ?"]
        params: list[Any] = [staff_id, guild_id]
        where_clause = " AND ".join(conditions)

        count_row = await self.fetch_one(
            f"SELECT COUNT(*) AS total FROM strikes WHERE {where_clause}",
            tuple(params),
        )
        total_count = count_row["total"] if count_row is not None else 0

        if not total_count:
            return {
                "success": False,
                "message": "No strikes found",
                "results": [],
                "page": page,
                "has_prev": False,
                "has_next": False,
                "total_count": 0,
                "max_page": 1,
            }

        max_page = max(1, -(-total_count // page_size))
        offset = (page - 1) * page_size

        query = f"""
            SELECT strike_id, reason, date, issued_by_id, type, expiry_date
            FROM strikes
            WHERE {where_clause}
            ORDER BY strike_id DESC
            LIMIT ? OFFSET ?
        """
        rows = await self.fetch_all(query, tuple(params) + (page_size + 1, offset))

        has_next = len(rows) > page_size
        rows = rows[:page_size]

        return {
            "success": True,
            "results": [
                {
                    "strike_id": row["strike_id"],
                    "reason": row["reason"],
                    "date": row["date"],
                    "manager": row["issued_by_id"],
                    "type": row["type"],
                    "expiry_date": row["expiry_date"],
                }
                for row in rows
            ],
            "page": page,
            "has_prev": page > 1,
            "has_next": has_next,
            "total_count": total_count,
            "max_page": max_page,
        }

    async def add_loa(
        self,
        guild_id: int,
        staff_id: int,
        reason: str,
        loa_issued_by: int,
    ) -> Dict[str, Any]:
        if not staff_id:
            return {"success": False, "message": "Missing staff_id"}

        if staff_id == loa_issued_by:
            return {"success": False, "message": "You cannot assign LOA to yourself"}

        row = await self.fetch_one(
            "SELECT on_loa FROM staffs WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id),
        )
        if row and row["on_loa"] == 1:
            return {"success": False, "message": "Staff is already on LOA"}
        
        has_permission: bool = await self.assert_staff_role_permission(staff_id, loa_issued_by, guild_id)
        if not has_permission:
            return {"success": False, "message": f"Action has been denied due to <@{staff_id}> having higher rank than you"}

        try:
            await self.execute(
                "UPDATE staffs SET on_loa = 1 WHERE staff_id = ? AND guild_id = ?",
                (staff_id, guild_id),
                commit=True,
            )

            started_on = datetime.now(timezone.utc).isoformat()
            await self.execute(
                """
                INSERT INTO leaves (staff_id, reason, issued_by, guild_id, started_on)
                VALUES (?, ?, ?, ?, ?)
                """,
                (staff_id, reason, loa_issued_by, guild_id, started_on),
                commit=True,
            )

            role_rows = await self.fetch_all(
                "SELECT role_id FROM staff_roles WHERE staff_id = ? AND guild_id = ?",
                (staff_id, guild_id),
            )
            roles_to_remove = [r["role_id"] for r in role_rows]

            roles_to_add: List[int] = []

            try:
                rows = await self.fetch_all(
                    """
                    SELECT role_id, role_type
                    FROM roles
                    WHERE guild_id = ?
                    AND role_type IN (?, ?)
                    """,
                    (guild_id, "staff_loa", "staff_base"),
                )

                roles = defaultdict(list)

                for row in rows:
                    roles[row["role_type"]].append(row["role_id"])

                roles_to_add.extend(roles["staff_loa"])
                roles_to_remove.extend(roles["staff_base"])

            except Exception as e:
                pass

            return {
                "success": True,
                "message": "Staff added to LOA successfully!",
                "roles_to_remove": roles_to_remove,
                "roles_to_add": roles_to_add,
            }

        except Exception as exc:
            return {"success": False, "message": str(exc)}

    async def remove_loa(self, staff_id: int, guild_id: int) -> Dict[str, Any]:
        if not staff_id:
            return {"success": False, "message": "Missing staff_id"}

        try:
            await self.execute(
                "UPDATE staffs SET on_loa = 0 WHERE staff_id = ? AND guild_id = ?",
                (staff_id, guild_id),
            )

            ended_on = datetime.now(timezone.utc).isoformat()

            await self.execute(
                """
                UPDATE leaves
                SET ended_on = ?
                WHERE leave_id = (
                    SELECT leave_id
                    FROM leaves
                    WHERE staff_id = ? AND guild_id = ?
                    ORDER BY leave_id DESC
                    LIMIT 1
                )
                """,
                (ended_on, staff_id, guild_id)
            )

            role_rows = await self.fetch_all(
                "SELECT role_id FROM staff_roles WHERE staff_id = ? AND guild_id = ?",
                (staff_id, guild_id),
            )
            roles_to_add = [r["role_id"] for r in role_rows]

            roles_to_remove: List[int] = []

            try:
                rows = await self.fetch_all(
                    """
                    SELECT role_id, role_type
                    FROM roles
                    WHERE guild_id = ?
                    AND role_type IN (?, ?)
                    """,
                    (guild_id, "staff_loa", "staff_base"),
                )

                roles = defaultdict(list)

                for row in rows:
                    roles[row["role_type"]].append(row["role_id"])

                roles_to_remove.extend(roles["staff_loa"])
                roles_to_add.extend(roles["staff_base"])

            except Exception as e:
                pass

            return {
                "success": True,
                "message": "Staff removed from LOA successfully!",
                "roles_to_add": roles_to_add,
                "roles_to_remove": roles_to_remove,
            }

        except Exception as exc:
            return {"success": False, "message": str(exc)}

    async def loa_list(self, staff_id: int, guild_id: int) -> List[Dict[str, Any]]:
        rows = await self.fetch_all(
            "SELECT leave_id, reason, issued_by FROM leaves WHERE staff_id = ? AND guild_id = ? ORDER BY leave_id DESC",
            (staff_id, guild_id)
        )

        return [
            {
                "leave_id": row["leave_id"],
                "reason": row["reason"],
                "issued_by": row["issued_by"]
            }
            for row in rows
        ]

    async def add_loa_pending(
        self,
        staff_id: int,
        guild_id: int,
        message_id: int,
        reason: str,
        days: str
    ):
        await self.ensure_staff(staff_id, guild_id)

        await self.execute(
            """
            INSERT INTO leaves_pending (
                staff_id,
                guild_id,
                message_id,
                reason,
                days
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                staff_id,
                guild_id,
                message_id,
                reason,
                days
            )
        )

    async def delete_loa_pending(self, staff_id: int, guild_id: int):
        await self.execute(
            "DELETE FROM leaves_pending WHERE staff_id = ? AND guild_id = ?",
            (staff_id, guild_id)
        )

    async def has_loa_pending(
        self,
        staff_id: int,
        guild_id: int
    ) -> tuple[bool, str | None, int | None]:
        result = await self.fetch_one(
            """
            SELECT id, reason
            FROM leaves_pending
            WHERE staff_id = ? AND guild_id = ?
            LIMIT 1
            """,
            (staff_id, guild_id)
        )

        if not result:
            return False, None, None

        loa_id, reason = result

        return True, reason, loa_id

    async def fetch_all_loa_pending(self) -> List[Dict]:
        rows = await self.fetch_all(
            """
            SELECT
                lp.staff_id,
                lp.guild_id,
                lp.reason,
                lp.days,
                lp.message_id,
                m.avatar_url AS staff_pfp
            FROM leaves_pending lp
            INNER JOIN members m
                ON lp.staff_id = m.member_id
                AND lp.guild_id = m.guild_id
            """
        )

        return [dict(row) for row in rows]

    async def delete_loa(self, leave_id: int):
        await self.execute("DELETE FROM leaves WHERE leave_id = ?", (leave_id,))

    async def fetch_loa_staffs(
        self, guild_id: int, role_type: str
    ) -> List[Dict[str, Any]]:
        rows = await self.fetch_all(
            """
            SELECT DISTINCT s.staff_id, s.joined_on, s.avatar_url
            FROM staffs s
            JOIN staff_roles sr ON s.staff_id = sr.staff_id AND s.guild_id = sr.guild_id
            JOIN roles r        ON sr.role_id  = r.role_id  AND sr.guild_id = r.guild_id
            WHERE s.on_loa = 1 AND s.guild_id = ? AND r.role_type = ?
            """,
            (guild_id, role_type),
        )

        result = []
        for row in rows:
            try:
                dt = datetime.strptime(row["joined_on"] or "01/01/2000", "%d/%m/%Y")
            except ValueError:
                dt = datetime(2000, 1, 1)

            result.append(
                {
                    "staff_id": row["staff_id"],
                    "joined_on": int(dt.timestamp()),
                    "avatar_url": row["avatar_url"],
                }
            )
        return result

    async def update_staff(
        self,
        guild_id: int,
        staff_id: int,
        update_type: str,
        reason: str,
        updated_by: int,
    ) -> Dict[str, Any]:
        if staff_id == updated_by:
            return {"success": False, "message": "You cannot update yourself."}
        if update_type not in ("promotion", "demotion"):
            return {"success": False, "message": "Invalid update_type."}

        current_role_row = await self.fetch_one(
            """
            SELECT sr.role_id, srk.priority, r.role_id AS _check
            FROM staff_roles sr
            JOIN roles r
                ON sr.role_id = r.role_id
            AND sr.guild_id = r.guild_id
            LEFT JOIN staff_ranks srk
                ON srk.role_id = r.role_id
            AND srk.guild_id = r.guild_id
            WHERE sr.staff_id = ?
            AND sr.guild_id = ?
            AND r.role_type = 'staff'
            ORDER BY srk.priority ASC
            LIMIT 1;
            """,
            (staff_id, guild_id),
        )
        if not current_role_row:
            return {"success": False, "message": "No staff role assigned."}

        current_role_id = current_role_row["role_id"]
        current_priority = current_role_row["priority"]

        updater_row = await self.fetch_one(
            """
            SELECT srk.priority
            FROM staff_roles sr
            JOIN roles r
                ON sr.role_id = r.role_id
            AND sr.guild_id = r.guild_id
            JOIN staff_ranks srk
                ON srk.role_id = r.role_id
            AND srk.guild_id = r.guild_id
            WHERE sr.staff_id = ?
            AND sr.guild_id = ?
            AND r.role_type = 'staff'
            ORDER BY srk.priority ASC
            LIMIT 1
            """,
            (updated_by, guild_id),
        )
        if not updater_row:
            return {"success": False, "message": "Updater has no staff role."}

        updater_priority = updater_row["priority"]

        if current_priority <= updater_priority:
            return {
                "success": False,
                "message": f"Action has been denied due to <@{staff_id}> having higher rank than you"
            }

        if update_type == "promotion":
            next_row = await self.fetch_one(
                """
                SELECT r.role_id, srk.priority
                FROM roles r
                JOIN staff_ranks srk
                    ON srk.role_id = r.role_id
                AND srk.guild_id = r.guild_id
                WHERE r.guild_id = ?
                AND r.role_type = 'staff'
                AND srk.priority < ?
                ORDER BY srk.priority DESC
                LIMIT 1;
                """,
                (guild_id, current_priority),
            )
        else:
            next_row = await self.fetch_one(
                """
                SELECT r.role_id, srk.priority
                FROM roles r
                JOIN staff_ranks srk
                    ON srk.role_id = r.role_id
                AND srk.guild_id = r.guild_id
                WHERE r.guild_id = ?
                AND r.role_type = 'staff'
                AND srk.priority > ?
                ORDER BY srk.priority ASC
                LIMIT 1
                """,
                (guild_id, current_priority),
            )

        if not next_row:
            label = "highest" if update_type == "promotion" else "lowest"
            return {"success": False, "message": f"Already at {label} role."}

        new_role_id = next_row["role_id"]
        new_priority = next_row["priority"]

        if new_priority < updater_priority:
            return {
                "success": False,
                "message": "You cannot update someone beyond your own role priority.",
            }

        await self.execute(
            """
            UPDATE staff_roles
            SET role_id = ?
            WHERE staff_id = ? AND guild_id = ? AND role_id = ?
            """,
            (new_role_id, staff_id, guild_id, current_role_id),
            commit=True,
        )

        await self.execute(
            """
            INSERT INTO rank_updates (
                guild_id, staff_id, updated_by,
                old_role_id, new_role_id, update_type, reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                staff_id,
                updated_by,
                current_role_id,
                new_role_id,
                update_type,
                reason,
            ),
            commit=True,
        )

        return {
            "success": True,
            "message": f"{update_type.title()} successful",
            "old_role_id": current_role_id,
            "new_role_id": new_role_id,
            "staff_id": staff_id,
        }

    async def add_staff_quota(
        self,
        guild_id: int,
        role_id: int,
        min_msg: int,
        min_ms: int,
        check_by: str,
    ) -> Dict[str, Any]:
        if check_by not in ("1d", "7d", "30d", None):
            return {
                "success": False,
                "message": "Invalid parameter type passed (check_by)",
            }

        await self.execute(
            """
            INSERT INTO staff_quota
                (role_id, guild_id, min_msg, min_ms, check_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                role_id,
                guild_id,
                min_msg,
                min_ms,
                check_by
            ),
        )
        return {"success": True, "message": "Quota Defined Successfully"}

    async def fetch_staff_quota(self, guild_id: int) -> List[Dict[str, Any]]:
        rows = await self.fetch_all(
            """
            SELECT quota_id, role_id, guild_id, min_msg, min_ms, check_by
            FROM staff_quota
            WHERE guild_id = ?
            """,
            (guild_id,),
        )
        return [
            {
                "quota_id": row["quota_id"],
                "role_id": row["role_id"],
                "guild_id": row["guild_id"],
                "min_msg": row["min_msg"],
                "min_ms": row["min_ms"],
                "check_by": row["check_by"]
            }
            for row in rows
        ]

    async def remove_staff_quota(self, guild_id: int, quota_id: int) -> Dict[str, Any]:
        await self.execute(
            "DELETE FROM staff_quota WHERE quota_id = ? AND guild_id = ?",
            (quota_id, guild_id),
        )
        return {"success": True, "message": "Quota removed successfully"}

    async def get_staff_current_quota(
        self, guild_id: int, staff_id: int
    ) -> Dict[str, Any]:
        msg_row = await self.fetch_one(
            """
            SELECT daily_messages, weekly_messages, monthly_messages, total_messages
            FROM messages
            WHERE member_id = ? AND guild_id = ?
            """,
            (staff_id, guild_id),
        )
        if not msg_row:
            daily = 0
            weekly = 0
            monthly = 0
            total = 0
        else:
            daily = msg_row["daily_messages"]
            weekly = msg_row["weekly_messages"]
            monthly = msg_row["monthly_messages"]
            total = msg_row["total_messages"]

        role_row = await self.fetch_one(
            """
            SELECT sr.role_id
            FROM staff_roles sr
            JOIN roles r
                ON sr.role_id = r.role_id
            AND sr.guild_id = r.guild_id
            LEFT JOIN staff_ranks srk
                ON srk.role_id = r.role_id
            AND srk.guild_id = r.guild_id
            WHERE sr.staff_id = ?
            AND sr.guild_id = ?
            AND r.role_type = 'staff'
            ORDER BY srk.priority ASC
            LIMIT 1;
            """,
            (staff_id, guild_id),
        )
        if not role_row:
            return {"success": False, "message": "Staff role not found"}

        role_id = role_row["role_id"]

        quota_row = await self.fetch_one(
            "SELECT min_msg, min_ms FROM staff_quota WHERE role_id = ? AND guild_id = ?",
            (role_id, guild_id),
        )
        if not quota_row:
            return {
                "success": False,
                "message": (
                    "No quota has been defined for any of the staff roles "
                    "assigned to this user. Please define a quota."
                ),
            }

        mod_stats = await self.fetch_mod_stats(
            guild_id=guild_id, moderator_id=staff_id, page_start=0, page_end=0
        )
        stats = mod_stats.get("stats") or {}
        weekly_ms = sum(v.get("7d", 0) for v in stats.values())

        min_msg = int(quota_row["min_msg"] or 0)
        min_ms = int(quota_row["min_ms"] or 0)

        return {
            "success": True,
            "message": "Quota fetched successfully.",
            "staff_id": staff_id,
            "guild_id": guild_id,
            "messages": {
                "daily": daily,
                "weekly": weekly,
                "monthly": monthly,
                "total": total,
            },
            "mod_stats_weekly": {"weekly_ms": weekly_ms},
            "quota": {"min_msg": min_msg, "min_ms": min_ms},
            "result": {
                "message_quota_passed": weekly >= min_msg,
                "ms_quota_passed": weekly_ms >= min_ms,
            },
        }

    async def update_message(self, staff_id: int, guild_id: int, avatar_url: str | None = None, name: str | None = None) -> None:

        """ Updating their profile each message to keep them upto date. """
        
        await self.execute(
                """
                INSERT INTO members (member_id, guild_id, avatar_url, name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(member_id, guild_id)
                DO UPDATE SET
                    avatar_url = excluded.avatar_url,
                    name = excluded.name
                """, (staff_id, guild_id, avatar_url, name)
        )
        await self.execute(
            """
            INSERT INTO messages (
                member_id, guild_id,
                daily_messages, weekly_messages, monthly_messages, total_messages
            )
            VALUES (?, ?, 1, 1, 1, 1)
            ON CONFLICT(member_id, guild_id) DO UPDATE SET
                daily_messages   = daily_messages   + 1,
                weekly_messages  = weekly_messages  + 1,
                monthly_messages = monthly_messages + 1,
                total_messages   = total_messages   + 1
            """,
            (staff_id, guild_id),
        )
            
    async def remove_role(self, guild_id: int, role_id: int) -> Dict[str, Any]:
        try:
            await self.execute(
                "DELETE FROM staff_roles WHERE role_id = ? AND guild_id = ?",
                (role_id, guild_id),
                commit=True,
            )
            await self.execute(
                "DELETE FROM staff_quota WHERE role_id = ? AND guild_id = ?",
                (role_id, guild_id),
                commit=True,
            )
            await self.execute(
                "DELETE FROM roles WHERE role_id = ? AND guild_id = ?",
                (role_id, guild_id),
                commit=True,
            )

            guild_cache = self.cache.get(guild_id)
            if guild_cache:
                guild_cache.get("roles", {}).pop(role_id, None)

            return {"success": True, "message": "Role removed successfully"}

        except Exception as exc:
            return {
                "success": False,
                "message": f"Role removal encountered an error: {exc}",
            }

    async def get_all_staff_quota_status(self, guild_id: int) -> Dict[str, Any]:
        quotas = await self.fetch_all(
            """
            SELECT quota_id, role_id, min_msg, min_ms,check_by
            FROM staff_quota WHERE guild_id = ?
            """,
            (guild_id,),
        )
        if not quotas:
            return {"success": False, "message": "No quotas defined for this guild"}

        quota_role_ids = [q["role_id"] for q in quotas if q["role_id"] is not None]
        if not quota_role_ids:
            return {"success": False, "message": "No valid quota roles found"}

        placeholders = ",".join("?" for _ in quota_role_ids)
        staff_rows = await self.fetch_all(
            f"""
            SELECT DISTINCT s.staff_id, s.name
            FROM staffs s
            JOIN staff_roles r ON s.staff_id = r.staff_id AND s.guild_id = r.guild_id
            WHERE s.guild_id = ? AND s.retired = 0 AND s.on_loa = 0
            AND r.role_id IN ({placeholders})
            """,
            (guild_id, *quota_role_ids),
        )
        if not staff_rows:
            return {
                "success": False,
                "message": "No applicable staff found for quota evaluation",
            }

        role_map_rows = await self.fetch_all(
            """
            SELECT sr.staff_id, sr.role_id
            FROM staff_roles sr
            JOIN roles r ON sr.role_id = r.role_id AND sr.guild_id = r.guild_id
            WHERE r.guild_id = ?
            """,
            (guild_id,),
        )
        staff_roles_map: Dict[int, list] = defaultdict(list)
        for row in role_map_rows:
            staff_roles_map[row["staff_id"]].append(row["role_id"])

        passed_staff: list = []
        failed_staff: list = []

        for staff_row in staff_rows:
            sid = staff_row["staff_id"]
            name = staff_row["name"]
            staff_roles = staff_roles_map.get(sid, [])

            applicable = [q for q in quotas if q["role_id"] in staff_roles]
            if not applicable:
                continue

            msg_row = await self.fetch_one(
                "SELECT weekly_messages FROM messages WHERE member_id = ? AND guild_id = ?",
                (sid, guild_id),
            )
            weekly_messages = msg_row["weekly_messages"] if msg_row else 0

            mod_stats = await self.fetch_mod_stats(
                guild_id=guild_id, moderator_id=sid, page_start=0, page_end=0
            )
            stats = mod_stats.get("stats") or {}
            weekly_ms = sum(v.get("7d", 0) for v in stats.values())

            staff_results: list = []
            staff_passed_any = False
            staff_fail_reasons: list = []

            for quota in applicable:
                msg_ok = int(weekly_messages or 0) >= int(quota["min_msg"] or 0)
                ms_ok = int(weekly_ms or 0) >= int(quota["min_ms"] or 0)
                quota_passed = msg_ok and ms_ok

                staff_results.append(
                    {
                        "quota_id": quota["quota_id"],
                        "role_id": quota["role_id"],
                        "passed": quota_passed,
                        "weekly_messages": weekly_messages,
                        "weekly_ms": weekly_ms,
                        "required": {
                            "min_msg": int(quota["min_msg"] or 0),
                            "min_ms": int(quota["min_ms"] or 0),
                        },
                        "failed_reasons": (
                            []
                            if quota_passed
                            else (
                                (["message_quota_failed"] if not msg_ok else [])
                                + (["mod_stats_failed"] if not ms_ok else [])
                            )
                        ),
                    }
                )
                if quota_passed:
                    staff_passed_any = True
                else:
                    staff_fail_reasons.append(f"quota_{quota['quota_id']}_failed")

            if staff_passed_any:
                passed_staff.append(
                    {"staff_id": sid, "name": name, "results": staff_results}
                )
            else:
                failed_staff.append(
                    {
                        "staff_id": sid,
                        "name": name,
                        "reasons": staff_fail_reasons,
                        "results": staff_results,
                    }
                )

        return {
            "success": True,
            "guild_id": guild_id,
            "summary": {
                "total_staff": len(staff_rows),
                "passed": len(passed_staff),
                "failed": len(failed_staff),
                "total_quotas": len(quotas),
            },
            "passed_staff": passed_staff,
            "failed_staff": failed_staff,
        }

    async def get_quota_status(self, guild_id: int, quota_id: int) -> Dict[str, Any]:
        quota = await self.fetch_one(
            """
            SELECT quota_id, role_id, min_msg, min_ms, check_by
            FROM staff_quota WHERE guild_id = ? AND quota_id = ?
            """,
            (guild_id, quota_id),
        )
        if not quota:
            return {"success": False, "message": f"No quota found with id {quota_id} for this guild"}

        PERIOD_TO_MSG_COL: Final = {
            "1d":  "daily_messages",
            "7d":  "weekly_messages",
            "30d": "monthly_messages",
        }
        PERIOD_TO_MOD_KEY: Final = {
            "1d":  "today",
            "7d":  "7d",
            "30d": "30d",
        }

        role_id  = quota["role_id"]
        min_msg  = int(quota["min_msg"] or 0)
        min_ms   = int(quota["min_ms"] or 0)
        check_by = (quota["check_by"] or "7d").strip().lower()

        msg_col = PERIOD_TO_MSG_COL.get(check_by, "weekly_messages")
        mod_key = PERIOD_TO_MOD_KEY.get(check_by, "7d")

        staff_rows = await self.fetch_all(
            """
            SELECT DISTINCT s.staff_id, s.name
            FROM staffs s
            JOIN staff_roles r
            ON s.staff_id = r.staff_id AND s.guild_id = r.guild_id
            WHERE s.guild_id = ?
            AND s.retired  = 0
            AND s.on_loa   = 0
            AND r.role_id  = ?
            """,
            (guild_id, role_id),
        )
        if not staff_rows:
            return {
                "success": False,
                "message": f"No active staff found under role <@&{role_id}> for quota {quota_id}",
            }

        passed_staff: list = []
        failed_staff: list = []

        for staff_row in staff_rows:
            sid  = staff_row["staff_id"]
            name = staff_row["name"]

            msg_row = await self.fetch_one(
                f"SELECT {msg_col} FROM messages WHERE member_id = ? AND guild_id = ?",
                (sid, guild_id),
            )
            period_messages = int(msg_row[msg_col] if msg_row else 0)

            mod_stats = await self.fetch_mod_stats(
                guild_id=guild_id, moderator_id=sid, page_start=0, page_end=0
            )
            stats = mod_stats.get("stats") or {}
            period_ms = sum(v.get(mod_key, 0) for v in stats.values())

            msg_ok = period_messages >= min_msg
            ms_ok = period_ms >= min_ms
            did_pass = msg_ok and ms_ok

            failed_reasons = []
            if not msg_ok:
                failed_reasons.append("message_quota_failed")
            if not ms_ok:
                failed_reasons.append("mod_stats_failed")

            staff_entry = {
                "staff_id":        sid,
                "name":            name,
                "passed":          did_pass,
                "period":          check_by,
                "period_messages": period_messages,
                "period_ms":       period_ms,
                "required": {
                    "min_msg": min_msg,
                    "min_ms":  min_ms,
                },
                "failed_reasons": failed_reasons,
            }

            if did_pass:
                passed_staff.append(staff_entry)
            else:
                failed_staff.append(staff_entry)

        return {
            "success":  True,
            "guild_id": guild_id,
            "quota": {
                "quota_id":        quota_id,
                "role_id":         role_id,
                "check_by":        check_by,
                "requirements": {
                    "min_msg": min_msg,
                    "min_ms":  min_ms,
                },
            },
            "summary": {
                "total_staff": len(staff_rows),
                "passed":      len(passed_staff),
                "failed":      len(failed_staff),
            },
            "passed_staff": passed_staff,
            "failed_staff": failed_staff,
        }

    async def get_quota_id_from_role(self, guild_id: int, role_id: int) -> int | None:
        row = await self.fetch_one(
            "SELECT quota_id FROM staff_quota WHERE guild_id = ? AND role_id = ?",
            (guild_id, role_id)
        )

        return row["quota_id"] if row else None
    
    async def get_quota_ids_from_checkby(
        self,
        guild_id: int,
        check_by: str
    ) -> list[int]:
        rows = await self.fetch_all(
            "SELECT quota_id FROM staff_quota WHERE guild_id = ? AND check_by = ?",
            (guild_id, check_by)
        )

        return [row["quota_id"] for row in rows]

    async def reset_messages(self, type: str) -> None:
        await self.execute(f"UPDATE messages SET {type}_messages = 0")

    async def get_role_mapping(self, member_id: int, guild_id: int) -> List[int]:
        rows = await self.fetch_all(
            "SELECT role_id FROM roles_customize WHERE member_id = ? AND guild_id = ?",
            (member_id, guild_id)
        )

        return [row["role_id"] for row in rows]
    
    async def add_role_mapping(
        self,
        member_id: int,
        guild_id: int,
        role_id: int
    ) -> None:
        await self.execute(
            """
            INSERT INTO roles_customize (
                member_id,
                guild_id,
                role_id
            )
            VALUES (?, ?, ?)
            ON CONFLICT(member_id, guild_id, role_id)
            DO NOTHING
            """,
            (member_id, guild_id, role_id)
        )

    async def remove_role_mapping(
        self,
        member_id: int,
        guild_id: int,
        role_id: int
    ) -> None:
        await self.execute(
            """
            DELETE FROM roles_customize
            WHERE member_id = ?
            AND guild_id = ?
            AND role_id = ?
            """,
            (member_id, guild_id, role_id)
        )
    
    async def ticket_stats(self, guild_id: int, staff_id: int) -> Dict[str, int]:
        rows = await self.fetch_all(
            """
            SELECT ticket_type, COUNT(*) AS count
            FROM ticket_logs
            WHERE staff_handled = ? AND guild_id = ?
            GROUP BY ticket_type
            """,
            (staff_id, guild_id)
        )

        return {
            row["ticket_type"].replace("_", " ").title(): row["count"]
            for row in rows
        } 

    async def rank_setup(self, guild_id: int, role_id: Dict[int, int]) -> None:
        sorted_roles = sorted(
            role_id.items(),
            key=lambda item: item[1],
            reverse=True
        )

        normalized = [
            (guild_id, role, priority)
            for priority, (role, _) in enumerate(sorted_roles)
        ]

        await self.execute(
            """
            DELETE FROM staff_ranks
            WHERE guild_id = ?
            """,
            (guild_id,)
        )

        await self.executemany(
            """
            INSERT INTO staff_ranks
                (guild_id, role_id, priority)
            VALUES (?, ?, ?)
            """,
            normalized
        )

    async def get_staff_ranks(self, guild_id: int) -> List[int]:
        rows = await self.fetch_all(
            "SELECT role_id FROM staff_ranks WHERE guild_id = ? ORDER BY priority ASC",
            (guild_id,)
        )
        return [row["role_id"] for row in rows]

    async def get_role_assignments(self, guild_id: int ,role_id: int) -> List[int]:
        rows = await self.fetch_all(
            "SELECT target_role_id FROM role_assignmnets WHERE guild_id = ? AND role_id = ?",
            (guild_id, role_id)
        )

        return [row["target_role_id"] for row in rows]

    async def get_staffs_timezone_coverage(self, guild_id: int) -> Dict[str, int]:
        rows = await self.fetch_all(
            """
            SELECT 
                m.timezone,
                COUNT(*) AS count
            FROM members m
            INNER JOIN staffs s
                ON s.staff_id = m.member_id
                AND s.guild_id = m.guild_id
            WHERE m.timezone IS NOT NULL
            AND m.guild_id = ?
            AND s.retired = 0
            GROUP BY m.timezone;
            """,
            (guild_id,)
        )

        return {
            row["timezone"]: row["count"]
            for row in rows
        }

    async def get_moderation_monthly_analysis(self, guild_id: int) -> List[Dict[str, Any]]:
        rows = await self.fetch_all(
            """
            SELECT
                strftime('%Y-%m-%d', timestamp) AS day,
                COUNT(*) AS total
            FROM modlogs
            WHERE guild_id = ?
            AND timestamp >= DATE('now', '-30 days')
            GROUP BY day
            ORDER BY day;
            """,
            (guild_id,)
        )

        return [
            {
                "day": row["day"],
                "total": row["total"]
            }
            for row in rows
        ]

    async def add_moderation_acronym(
        self,
        member_id: int,
        guild_id: int,
        key: str,
        value: str
    ) -> None:
        key = key.lower().strip()

        row = await self.fetch_one(
            """
            SELECT acronyms
            FROM acronyms
            WHERE member_id = ? AND guild_id = ?
            """,
            (member_id, guild_id)
        )

        if row:
            data: dict[str, str] = {
                k.lower().strip(): v
                for k, v in json.loads(row[0] or "{}").items()
            }
        else:
            data = {}

        data[key] = value

        await self.execute(
            """
            INSERT INTO acronyms (member_id, guild_id, acronyms)
            VALUES (?, ?, ?)
            ON CONFLICT(member_id, guild_id)
            DO UPDATE SET acronyms = excluded.acronyms
            """,
            (
                member_id,
                guild_id,
                json.dumps(data)
            )
        )

    async def remove_moderation_acronym(
        self,
        member_id: int,
        guild_id: int,
        key: str
    ) -> None:
        row = await self.fetch_one(
            """
            SELECT acronyms
            FROM acronyms
            WHERE member_id = ? AND guild_id = ?
            """,
            (member_id, guild_id)
        )

        data: dict[str, str] = json.loads(row[0] or "{}")

        key = key.lower()

        del data[key]

        await self.execute(
            """
            UPDATE acronyms
            SET acronyms = ?
            WHERE member_id = ? AND guild_id = ?
            """,
            (
                json.dumps(data),
                member_id,
                guild_id
            )
        )

    async def update_moderation_acronym(
        self,
        member_id: int,
        guild_id: int,
        key: str,
        value: str
    ) -> None:
        row = await self.fetch_one(
            """
            SELECT acronyms
            FROM acronyms
            WHERE member_id = ? AND guild_id = ?
            """,
            (member_id, guild_id)
        )

        data: dict[str, str] = json.loads(row[0] or "{}")

        key = key.lower()


        data[key] = value

        await self.execute(
            """
            UPDATE acronyms
            SET acronyms = ?
            WHERE member_id = ? AND guild_id = ?
            """,
            (
                json.dumps(data),
                member_id,
                guild_id
            )
        )

    async def get_moderation_acronyms(
        self,
        member_id: int,
        guild_id: int
    ) -> Dict[str, str]:
        row = await self.fetch_one(
            """
            SELECT acronyms
            FROM acronyms
            WHERE member_id = ? AND guild_id = ?
            """,
            (member_id, guild_id)
        )

        if not row:
            return {}

        return json.loads(row[0] or "{}") 
    
    async def upsert_appeal_forum(
        self,
        guild_id: int,
        config: str,
    ):
        await self.execute(
            """
            INSERT INTO mod_appeal_forum (guild_id, config)
            VALUES (?, ?)
            ON CONFLICT(guild_id)
            DO UPDATE SET
                config = excluded.config
            """,
            (guild_id, config),
        )


    async def get_appeal_forum_config(
        self,
        guild_id: int,
    ) -> List[Dict[str, str]]:
        row = await self.fetch_one(
            "SELECT config FROM mod_appeal_forum WHERE guild_id = ?",
            (guild_id,),
        )

        if row is None:
            return []

        return json.loads(row["config"])
    
    async def appeal_exists(
        self,
        case_id: int,
    ) -> bool:
        row = await self.fetch_one(
            "SELECT 1 FROM mod_appeal WHERE case_id = ?",
            (case_id,),
        )

        return row is not None
    
    async def create_appeal(
        self,
        case_id: int,
        thread_id: int
    ):
        await self.execute(
            "INSERT INTO mod_appeal (case_id, status, thread_id) VALUES (?, ?, ?)", (case_id, "pending", thread_id)
        )

    async def get_appeal_status(
        self,
        case_id: int,
    ) -> Optional[str]:
        row = await self.fetch_one(
            "SELECT status FROM mod_appeal WHERE case_id = ?",
            (case_id,),
        )

        if row is None:
            return None

        return row["status"]
    
    async def set_appeal_status(
        self,
        case_id: int,
        status: str,
    ) -> None:
        await self.execute(
            """
            UPDATE mod_appeal
            SET status = ?
            WHERE case_id = ?
            """,
            (status, case_id),
        )

    async def get_appeal(
        self,
        thread_id: int,
    ) -> Optional[Dict[str, Any]]:
        row = await self.fetch_one(
            """
            SELECT
                *
            FROM mod_appeal
            WHERE thread_id = ?
            """,
            (thread_id,),
        )

        if row is None:
            return None

        return dict(row)
    
    async def get_appeal_complete(
        self,
        thread_id: int
    ) -> Optional[Dict[str, Any]]:
        row = await self.fetch_one(
            """
            SELECT ma.*,
            m.*
            FROM mod_appeal AS ma
            JOIN modlogs AS m
                ON ma.case_id = m.id
            WHERE
                ma.thread_id = ?
                AND ma.status = 'pending'
            """,
            (thread_id,),
        )

        return dict(row) if row else None

    async def get_current_active_appeal(self, member_id: int):
        row = await self.fetch_one(
            """
            SELECT ma.*,
            m.guild_id as guild_id
            FROM mod_appeal AS ma
            JOIN modlogs AS m
                ON ma.case_id = m.id
            WHERE
                m.target_user_id = ?
                AND ma.status = 'pending'
            ORDER BY m.id DESC
            LIMIT 1;
            """,
            (member_id,),
        )

        return dict(row) if row else None

    async def leaderboard(self, guild_id: int, leaderboard_type: int) -> Dict[str, Any]:
        types = {
            0: "daily_messages",
            1: "weekly_messages",
            2: "monthly_messages",
            3: "total_messages",
        }

        column = types.get(leaderboard_type)

        if column is None:
            return {
                "success": False,
                "error": "Invalid leaderboard type",
                "leaderboard": []
            }

        query = f"""
            SELECT
                m.member_id,
                m.name,
                m.avatar_url,
                msg.{column} AS messages
            FROM messages msg
            INNER JOIN members m
                ON m.member_id = msg.member_id
                AND m.guild_id = msg.guild_id
            WHERE msg.guild_id = ?
            ORDER BY msg.{column} DESC
            LIMIT 100
        """

        rows= await self.fetch_all(query, (guild_id,))

        leaderboard = []

        for index, row in enumerate(rows, start=1):
            leaderboard.append({
                "rank": index,
                "member_id": row["member_id"],
                "name": row["name"],
                "avatar_url": row["avatar_url"],
                "messages": row["messages"]
            })

        return {
            "success": True,
            "guild_id": guild_id,
            "type": column.replace("_messages", ""),
            "count": len(leaderboard),
            "leaderboard": leaderboard
        }

    async def get_timezone(
        self,
        member_id: int,
        guild_id: int
    ) -> str | None:
        row = await self.fetch_one(
            """
            SELECT timezone
            FROM members
            WHERE member_id = ? AND guild_id = ?
            """,
            (member_id, guild_id)
        )

        return row["timezone"] if row else None


    async def set_timezone(
        self,
        member_id: int,
        guild_id: int,
        timezone: str
    ) -> bool:
        await self.execute(
            """
            INSERT INTO members (member_id, guild_id, timezone)
            VALUES (?, ?, ?)
            ON CONFLICT (member_id, guild_id)
            DO UPDATE SET timezone = excluded.timezone
            """,
            (member_id, guild_id, timezone)
        )

        return True