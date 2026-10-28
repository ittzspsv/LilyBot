from datetime import timedelta

import discord

from ..access import LilyDatabaseAccess

BULK_DELETE_MAX_AGE = timedelta(days=14)


class ArchiveAccess(LilyDatabaseAccess):
    async def load_cache(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL
            )
        """)
        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_guild_author
            ON messages (guild_id, author_id)
        """)

    async def record_message(
        self, message_id: int, channel_id: int, guild_id: int, author_id: int
    ) -> None:
        await self.execute(
            "INSERT OR IGNORE INTO messages (message_id, channel_id, guild_id, author_id) VALUES (?, ?, ?, ?)",
            (message_id, channel_id, guild_id, author_id),
        )

    async def remove_messages(self, message_ids: list[int]) -> None:
        if message_ids:
            await self.executemany(
                "DELETE FROM messages WHERE message_id = ?",
                [(i,) for i in message_ids],
            )

    async def get_user_message_ids(
        self,
        guild_id: int,
        author_id: int,
        limit: int,
        *,
        margin: timedelta = timedelta(hours=2),
    ) -> dict[int, list[int]]:
        floor = discord.utils.time_snowflake(
            discord.utils.utcnow() - BULK_DELETE_MAX_AGE + margin
        )
        rows = await self.fetch_all(
            """
            SELECT channel_id, message_id FROM messages
            WHERE guild_id = ? AND author_id = ? AND message_id >= ?
            ORDER BY message_id DESC
            LIMIT ?
            """,
            (guild_id, author_id, floor, limit),
        )

        grouped: dict[int, list[int]] = {}
        for channel_id, message_id in rows:
            grouped.setdefault(channel_id, []).append(message_id)
        return grouped

    async def delete_expired(self) -> int:
        cutoff = discord.utils.time_snowflake(
            discord.utils.utcnow() - BULK_DELETE_MAX_AGE
        )
        return await self.execute(
            "DELETE FROM messages WHERE message_id < ?",
            (cutoff,),
            row_count=True,
        ) or 0