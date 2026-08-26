from ..sLilyDatabaseAccess import LilyDatabaseAccess


class LevelingManagement:
    def __init__(self, db: LilyDatabaseAccess):
        super().__init__()

        self.db: LilyDatabaseAccess = db

    async def get_leveling_info(self, guild_id: int, member_id: int):
        result = await self.db.fetch_one(
            """
            SELECT
                COALESCE(total_messages, 0) AS total_messages,
                COALESCE(
                    RANK() OVER (
                        PARTITION BY guild_id
                        ORDER BY total_messages DESC
                    ),
                    0
                ) AS rank
            FROM messages
            WHERE guild_id = ?
            AND member_id = ?
            """,
            (guild_id, member_id)
        )

        if result is None:
            return {
                "total_messages": 0,
                "rank": 0
            }

        return dict(result)