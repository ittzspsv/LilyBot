from ..access import LilyDatabaseAccess

from typing import List, Tuple


class LevelingManagement:
    def __init__(self, db: LilyDatabaseAccess):
        super().__init__()

        self.db: LilyDatabaseAccess = db

    async def get_leveling_info(self, guild_id: int, member_id: int):
        result = await self.db.fetch_one(
            """
            SELECT total_xp, rank
            FROM (
                SELECT
                    member_id,
                    total_xp,
                    RANK() OVER (
                        PARTITION BY guild_id
                        ORDER BY total_xp DESC
                    ) AS rank
                FROM messages
                WHERE guild_id = ?
            ) AS ranked
            WHERE member_id = ?
            """,
            (guild_id, member_id),
        )

        if result is None:
            return {
                "total_xp": 0,
                "rank": 0
            }

        return dict(result)

    async def set_leveling_role(
        self,
        guild_id: int,
        role_id: List[int],
        level: int
    ) -> None:
        await self.db.executemany(
            """
            INSERT INTO leveling (guild_id, role_id, level)
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id, role_id)
            DO UPDATE SET level = excluded.level
            """,
            [
                (guild_id, role, level)
                for role in role_id
            ]
        )

    async def get_roles_based_on_level(
        self,
        guild_id: int,
        level: int
    ) -> List[int]:
        rows = await self.db.fetch_all(
            """
            SELECT role_id
            FROM leveling
            WHERE guild_id = ?
            AND level = ?
            """,
            (guild_id, level)
        )

        return [row[0] for row in rows]

    async def get_all_leveling_roles(
        self,
        guild_id: int
    ) -> List[Tuple[int, int]]:
        rows = await self.db.fetch_all(
            """
            SELECT role_id, level
            FROM leveling
            WHERE guild_id = ?
            ORDER BY level ASC
            """,
            (guild_id,)
        )

        return [(row[0], row[1]) for row in rows]

    async def remove_leveling_role(
        self,
        guild_id: int,
        role_id: int
    ) -> bool:
        """Returns True if a row was actually deleted, False if none matched."""
        result = await self.db.execute(
            """
            DELETE FROM leveling
            WHERE guild_id = ?
            AND role_id = ?
            """,
            (guild_id, role_id),
            row_count=True
        )
        return result > 0 if result else False