import asqlite
from contextlib import asynccontextmanager
from typing import Optional


class LilyDatabaseAccess:
    def __init__(self) -> None:
        self.pool: Optional[asqlite.Pool] = None
        self.cache = {}

    @classmethod
    async def connect(cls, db_path: str = "database.db", pool_size: int = 4):
        self = cls()
        self.pool = await asqlite.create_pool(db_path, size=pool_size)
        await self.load_cache()
        return self

    async def refresh_cache(self):
        await self.load_cache()

    def _validate_pool(self) -> asqlite.Pool:
        if self.pool is None:
            raise RuntimeError("Database pool not connected")
        return self.pool
    
    @asynccontextmanager
    async def transaction(self):
        pool = self._validate_pool()
        async with pool.acquire() as conn:
            try:
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def execute(
        self,
        query: str,
        params: tuple = (),
        commit: bool = True,
        row_count: bool = False
    ) -> Optional[int]:
        pool = self._validate_pool()

        async with pool.acquire() as conn:
            cursor = await conn.execute(query, params)

            if commit:
                await conn.commit()

            if row_count:
                return cursor.get_cursor().rowcount

            return cursor.get_cursor().lastrowid

    async def executemany(self, query: str, params: list[tuple], commit: bool = True) -> None:
        pool = self._validate_pool()
        async with pool.acquire() as conn:
            await conn.executemany(query, params)
            if commit:
                await conn.commit()

    async def fetch_one(self, query: str, params: tuple = ()):
        pool = self._validate_pool()
        async with pool.acquire() as conn:
            return await conn.fetchone(query, params)

    async def fetch_all(self, query: str, params: tuple = ()):
        pool = self._validate_pool()
        async with pool.acquire() as conn:
            return await conn.fetchall(query, params)

    async def load_cache(self):
        raise NotImplementedError

    async def close(self):
        pool = self._validate_pool()
        await pool.close()