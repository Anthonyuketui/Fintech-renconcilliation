"""Handles report storage in AWS S3 or a local fallback."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError

logger = logging.getLogger(__name__)


class AWSManager:
    """Uploads files to S3 and generates presigned URLs.

    If AWS credentials or a bucket are not configured, the manager falls
    back to leaving files on the local file system.  The caller can
    detect this by examining the returned key/path.
    """

    def __init__(self, bucket_name: Optional[str] = None, region: Optional[str] = None):
        self.bucket_name = bucket_name or os.getenv("AWS_S3_BUCKET_NAME")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.s3_client = None
        # Lazily initialize the boto3 client if credentials are present
        if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY") and self.bucket_name:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=self.region,
            )
        else:
            logger.info("AWS credentials or bucket not fully configured; using local fallback")

    def upload_report(self, file_path: Path, key: Optional[str] = None) -> str:
        """Upload a report file to S3 or return a local path.

        Args:
            file_path: Path to the local file to upload.
            key: Optional object key to use in S3.  If omitted the file name
                is used.

        Returns:
            If uploaded to S3, returns the S3 object key.  Otherwise returns
            the absolute path of the local file.
        """
        if not self.s3_client or not self.bucket_name:
            # Simply return path; caller may treat this as local storage
            return str(file_path.resolve())
        key = key or file_path.name
        try:
            self.s3_client.upload_file(str(file_path), self.bucket_name, key)
            logger.info("Uploaded report to S3 bucket %s as %s", self.bucket_name, key)
            return key
        except (BotoCoreError, NoCredentialsError) as exc:
            logger.exception("Failed to upload to S3, falling back to local storage: %s", exc)
            return str(file_path.resolve())

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        """Generate a presigned URL for an S3 object if possible.

        Args:
            key: The object key in the configured bucket.
            expires_in: Expiration time in seconds.

        Returns:
            A URL string if generation succeeds; otherwise None.
        """
        if not self.s3_client or not self.bucket_name:
            return None
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except (BotoCoreError, NoCredentialsError) as exc:
            logger.warning("Unable to generate presigned URL: %s", exc)
            return None