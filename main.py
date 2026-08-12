import os
import asyncio
import logging

from src.core.backups import ObjectStorageService
from src.lily import Lily

from dotenv import load_dotenv
from pathlib import Path

load_dotenv("token.env")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("lily")


async def lily_bot():
    bot = Lily()

    token = os.getenv("token")
    if not token:
        raise ValueError("TOKEN environment variable is missing")

    logger.info("Starting Lily")

    await bot.start(token=token)

    """ 
    Note: 
        * You can obviously implement your own backup system, If the bot is used by a big server
        * I went with this approach on storing it on a object storage because I want backups to happen outside of the VPS
        * You can also put this inside src/lily.py and use discord.py library tasks instead, If you prefer. Just upto you

        from discord.ext import tasks

        @tasks.loop(hours=6)
        async def backup(self):
            await _s3.backup_job(
                file_path
            )

        Don't forgot to start this task using `self.backup.start()`

        * If no environment variables has been set up, the backup won't start         
    """

    endpoint_url = os.getenv("OBJECT_STORAGE_ENDPOINT_URL")
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    region_name = os.getenv("REGION_NAME")
    bucket = os.getenv("BUCKET")

    BASE_DIR = Path(__file__).resolve().parent
    path = BASE_DIR / "storage" / "configs" / "Configs.db"

    if (
        not endpoint_url
        or not aws_access_key_id
        or not aws_secret_access_key
        or not region_name
        or not bucket
    ):
        logger.warning(
            "Object storage configuration is incomplete. "
            "Automatic database backups are disabled."
        )
    else:
        _s3 = ObjectStorageService(
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
            bucket=bucket,
        )

        _s3.start_backup_scheduler(
            path
        )

        logger.info(
            "Backup scheduling started. %s will be backed up every 6 hours.",
            path,
        )


asyncio.run(lily_bot())