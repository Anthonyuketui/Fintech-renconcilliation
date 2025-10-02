"""Handles report storage in AWS S3 or a local fallback."""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

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
        self._s3_available = False

        # Lazily initialize the boto3 client if credentials are present
        if (
            os.getenv("AWS_ACCESS_KEY_ID")
            and os.getenv("AWS_SECRET_ACCESS_KEY")
            and self.bucket_name
        ):
            try:
                self.s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                    region_name=self.region,
                )
                # Validate credentials immediately
                self._validate_credentials()
            except Exception as exc:
                logger.warning(
                    "Failed to initialize S3 client: %s. Using local fallback.", exc
                )
                self.s3_client = None
        else:
            logger.info(
                "AWS credentials or bucket not fully configured; using local fallback"
            )

    def _validate_credentials(self) -> None:
        """Validate AWS credentials and bucket access during initialization."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            self._s3_available = True
            logger.info(
                "AWS S3 validated successfully for bucket: %s", self.bucket_name
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            logger.warning(
                "AWS credentials invalid or bucket inaccessible (%s): %s. Using local fallback.",
                error_code,
                self.bucket_name,
            )
            self.s3_client = None
            self._s3_available = False
        except Exception as exc:
            logger.warning(
                "Failed to validate S3 access: %s. Using local fallback.", exc
            )
            self.s3_client = None
            self._s3_available = False

    def upload_report(self, file_path: Path, key: Optional[str] = None) -> str:
        """Upload a report file to S3 or return a local path.

        Args:
            file_path: Path to the local file to upload.
            key: Optional object key to use in S3.  If omitted, creates
                organized path with date and filename.

        Returns:
            If uploaded to S3, returns the S3 object key (e.g., "reports/2025-10-01/file.csv").
            If using local fallback, returns path with "file://" prefix
            (e.g., "file:///absolute/path/to/file.csv").

        Raises:
            FileNotFoundError: If the file_path doesn't exist.
        """
        # Validate file exists before attempting anything
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Use local storage if S3 is not available
        if not self._s3_available or not self.s3_client or not self.bucket_name:
            return self._use_local_storage(file_path)

        # Enhanced key generation with date organization for production
        if not key:
            date_str = date.today().strftime("%Y-%m-%d")
            key = f"reports/{date_str}/{file_path.name}"

        try:
            # Upload with metadata and encryption for production security
            self.s3_client.upload_file(
                str(file_path),
                self.bucket_name,
                key,
                ExtraArgs={
                    "Metadata": {
                        "upload_date": date.today().isoformat(),
                        "system": "fintech_reconciliation",
                        "file_type": file_path.suffix.lstrip(".") or "unknown",
                    },
                    "ServerSideEncryption": "AES256",  # Encrypt at rest
                    "ContentType": self._get_content_type(file_path),
                },
            )
            logger.info("Uploaded report to S3 bucket %s as %s", self.bucket_name, key)
            return key

        except NoCredentialsError:
            logger.error("AWS credentials not found, falling back to local storage")
            self._s3_available = False  # Disable for future calls
            return self._use_local_storage(file_path)

        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")

            # For certain errors, fall back to local storage
            if error_code in (
                "NoSuchBucket",
                "AccessDenied",
                "InvalidAccessKeyId",
                "SignatureDoesNotMatch",
            ):
                logger.error(
                    "S3 access error (%s), falling back to local storage", error_code
                )
                self._s3_available = False  # Disable for future calls
                return self._use_local_storage(file_path)
            else:
                # Other errors might be transient
                logger.exception("S3 client error during upload")
                raise

        except BotoCoreError:
            logger.exception(
                "BotoCore error during S3 upload, falling back to local storage"
            )
            return self._use_local_storage(file_path)

        except Exception:
            logger.exception("Unexpected error during S3 upload")
            raise

    def _use_local_storage(self, file_path: Path) -> str:
        """Return local file path with file:// prefix.

        Args:
            file_path: Path to the local file.

        Returns:
            Local file path with "file://" prefix and forward slashes.
        """
        local_path = file_path.resolve().as_posix()
        return f"file://{local_path}"

    def is_s3_path(self, path: str) -> bool:
        """Check if a path is an S3 key or local file path.

        Args:
            path: Path string to check.

        Returns:
            True if S3 key, False if local path.
        """
        return not path.startswith("file://")

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        """Generate a presigned URL for an S3 object if possible.

        Args:
            key: The object key in the configured bucket (not a file:// path).
            expires_in: Expiration time in seconds (default: 1 hour).

        Returns:
            A URL string if generation succeeds; otherwise None.
        """
        # Don't try to generate URLs for local paths
        if key.startswith("file://"):
            logger.debug("Cannot generate presigned URL for local path: %s", key)
            return None

        if not self.s3_client or not self.bucket_name:
            return None

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            logger.debug(
                "Generated presigned URL for %s (expires in %d seconds)",
                key,
                expires_in,
            )
            return url
        except (BotoCoreError, NoCredentialsError, ClientError) as exc:
            logger.warning("Unable to generate presigned URL for %s: %s", key, exc)
            return None

    def _get_content_type(self, file_path: Path) -> str:
        """Determine appropriate content type based on file extension."""
        suffix = file_path.suffix.lower()
        content_types = {
            ".csv": "text/csv",
            ".json": "application/json",
            ".txt": "text/plain",
            ".pdf": "application/pdf",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        return content_types.get(suffix, "application/octet-stream")

    def health_check(self) -> bool:
        """Check S3 connectivity and bucket access."""
        if not self.s3_client or not self.bucket_name:
            logger.info("S3 health check: using local fallback mode")
            return True  # Local fallback is healthy

        try:
            # Test bucket access
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info("S3 health check passed for bucket: %s", self.bucket_name)
            self._s3_available = True
            return True
        except Exception as exc:
            logger.error("S3 health check failed: %s", exc)
            self._s3_available = False
            return False

    def list_recent_reports(
        self, prefix: str = "reports/", max_keys: int = 100
    ) -> list:
        """List recent reports from S3 bucket.

        Args:
            prefix: S3 key prefix to filter objects
            max_keys: Maximum number of objects to return

        Returns:
            List of dictionaries with object metadata, or empty list if S3 unavailable
        """
        if not self.s3_client or not self.bucket_name:
            logger.info("Cannot list reports: S3 not configured")
            return []

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=prefix, MaxKeys=max_keys
            )

            reports = []
            for obj in response.get("Contents", []):
                reports.append(
                    {
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                        "presigned_url": self.generate_presigned_url(
                            obj["Key"], expires_in=86400
                        ),  # 24 hours
                    }
                )

            logger.info("Listed %d reports from S3", len(reports))
            return reports

        except Exception as exc:
            logger.error("Failed to list reports from S3: %s", exc)
            return []
