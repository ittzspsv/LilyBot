from pathlib import Path
from typing import BinaryIO

import boto3
import zipfile
import asyncio


from datetime import datetime, timezone
from botocore.exceptions import ClientError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


class ObjectStorageService:
    def __init__(
            self, 
            endpoint_url: str, 
            aws_access_key_id: str, 
            aws_secret_access_key: str, 
            region_name: str, 
            bucket: str
        ) -> None:
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )

        self.scheduler = AsyncIOScheduler(timezone="UTC")

        self.bucket = bucket

    def upload_file(
        self,
        file_path: str | Path,
        object_key: str,
        content_type: str | None = None,
    ) -> None:
        """
        Upload a local file directly to object storage.
        """

        extra_args = {}

        if content_type:
            extra_args["ContentType"] = content_type

        self.client.upload_file(
            Filename=str(file_path),
            Bucket=self.bucket,
            Key=object_key,
            ExtraArgs=extra_args or None,
        )

    def upload_bytes(
        self,
        data: bytes,
        object_key: str,
        content_type: str | None = None,
    ) -> None:
        """
        Upload raw bytes directly to object storage.
        """

        extra_args = {}

        if content_type:
            extra_args["ContentType"] = content_type

        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=data,
            **extra_args,
        )

    def upload_stream(
        self,
        file_obj: BinaryIO,
        object_key: str,
        content_type: str | None = None,
    ) -> None:
        """
        Upload a file-like object to object storage.
        """

        extra_args = {}

        if content_type:
            extra_args["ContentType"] = content_type

        self.client.upload_fileobj(
            file_obj,
            self.bucket,
            object_key,
            ExtraArgs=extra_args or None,
        )

    def generate_upload_url(
        self,
        object_key: str,
        content_type: str | None = None,
        expires_in: int = 300,
    ) -> str:
        params = {
            "Bucket": self.bucket,
            "Key": object_key,
        }

        if content_type:
            params["ContentType"] = content_type

        return self.client.generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=expires_in,
        )

    def generate_read_url(
        self,
        object_key: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Generate a presigned URL for downloading/reading an object.
        """

        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": object_key,
            },
            ExpiresIn=expires_in,
        )
    
    def delete_object(self, object_key: str) -> None:
        """Delete an object from storage."""

        self.client.delete_object(
            Bucket=self.bucket,
            Key=object_key,
        )

    def object_exists(self, object_key: str) -> bool:
        """Check whether an object exists."""

        try:
            self.client.head_object(
                Bucket=self.bucket,
                Key=object_key,
            )
            return True

        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False

            raise

    def get_object_size(self, object_key: str) -> int:
        """Return object size in bytes."""

        response = self.client.head_object(
            Bucket=self.bucket,
            Key=object_key,
        )

        return response["ContentLength"]

    async def backup_job(
        self,
        file_path: str | Path,
        object_prefix: str = "backups",
    ) -> None:
        """
        Zip the backup file and upload it to object storage.
        """

        file_path = Path(file_path)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        zip_path = file_path.with_name(
            f"{file_path.stem}_{timestamp}.zip"
        )

        object_key = f"{object_prefix}/{zip_path.name}"

        try:
            def create_zip() -> None:
                with zipfile.ZipFile(
                    zip_path,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                ) as archive:
                    archive.write(
                        file_path,
                        arcname=file_path.name,
                    )

            await asyncio.to_thread(create_zip)

            await asyncio.to_thread(
                self.upload_file,
                zip_path,
                object_key,
                "application/zip",
            )

        finally:
            if zip_path.exists():
                zip_path.unlink()

    def start_backup_scheduler(
        self,
        file_path: str | Path,
        object_prefix: str = "backups",
    ) -> None:
        self.scheduler.add_job(
            self.backup_job,
            trigger=CronTrigger(
                hour="*/6",
                minute=0,
                timezone="UTC",
            ),
            args=[file_path, object_prefix],
            id="database_backup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        self.scheduler.start()
    