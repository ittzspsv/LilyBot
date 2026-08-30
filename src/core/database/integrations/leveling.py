from ..access import LilyDatabaseAccess


class LevelingManagement:
    def __init__(self, db: LilyDatabaseAccess):
        super().__init__()

        self.db: LilyDatabaseAccess = db

    async def get_leveling_info(self, guild_id: int, member_id: int):
        result = await self.db.fetch_one(
            """
            SELECT total_messages, rank
            FROM (
                SELECT
                    member_id,
                    total_messages,
                    RANK() OVER (
                        PARTITION BY guild_id
                        ORDER BY total_messages DESC
                    ) AS rank
                FROM messages
                WHERE guild_id = ?
            ) AS ranked
            WHERE member_id = ?
            """,
            (guild_id, member_id)
        )

        if result is None:
            return {
                "total_messages": 0,
                "rank": 0
            }

        return dict(result)