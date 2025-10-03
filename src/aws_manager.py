"""
aws_manager.py

## AWS S3 Storage Manager with Local Fallback 

This module provides the AWSManager class for handling report persistence.
It prioritizes secure, permanent storage in AWS S3 but implements a robust
local file system fallback if S3 credentials, configuration,
or access fails, ensuring the reconciliation process never stalls due to storage issues.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

# Use an explicit logger for production traceability
logger = logging.getLogger(__name__)


class AWSManager:
    """
    Manages report storage, defaulting to S3 and falling back to local files.

    Returns the S3 object key or a local "file://" prefixed path, allowing
    the caller to transparently handle either storage location.
    """

    def __init__(self, bucket_name: Optional[str] = None, region: Optional[str] = None):
        """Initializes S3 configuration and client, validating access immediately."""
        self.bucket_name = bucket_name or os.getenv("AWS_S3_BUCKET_NAME")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.s3_client = None
        self._s3_available = False

        self._initialize_s3_client()

    def _initialize_s3_client(self):
        """Initializes and validates the S3 client, setting _s3_available."""
        if not self.bucket_name:
            logger.info("AWS S3 bucket name not configured; using local fallback.")
            return

        # Check for credentials directly to avoid unnecessary client instantiation
        if (
            not os.getenv("AWS_ACCESS_KEY_ID")
            or not os.getenv("AWS_SECRET_ACCESS_KEY")
        ):
            logger.info("AWS credentials not found; using local fallback.")
            return

        try:
            # Instantiate client
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=self.region,
            )
            # Validate credentials and bucket access
            self._validate_credentials()

        except Exception as exc:
            logger.warning(
                "Failed to initialize S3 client: %s. Using local fallback.", exc
            )
            self.s3_client = None
            self._s3_available = False

    def _validate_credentials(self) -> None:
        """
        Validates AWS credentials and bucket access during initialization.

        Sets `self._s3_available` flag.
        """
        if not self.s3_client or not self.bucket_name:
            self._s3_available = False
            return

        try:
            # `head_bucket` is a lightweight call to check if the bucket exists and we can access it
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            self._s3_available = True
            logger.info(
                "AWS S3 validated successfully for bucket: %s", self.bucket_name
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            logger.warning(
                "AWS credentials invalid or bucket inaccessible (%s). Falling back to local.",
                error_code,
            )
            self._s3_available = False
            self.s3_client = None # Clear client to prevent reuse

        except Exception as exc:
            logger.warning(
                "Failed to validate S3 access: %s. Falling back to local.", exc
            )
            self._s3_available = False
            self.s3_client = None # Clear client to prevent reuse


    def upload_report(self, file_path: Path, key: Optional[str] = None) -> str:
        """
        Uploads a report file to S3. Falls back to local storage on failure.

        Args:
            file_path: Path to the local file to upload.
            key: Optional S3 object key. Defaults to `reports/{date}/{filename}`.

        Returns:
            The S3 object key (e.g., "reports/2025-10-01/file.csv") or
            the local path prefixed with "file://" (e.g., "file:///abs/path/to/file.csv").
        """
        # 1. Pre-flight check
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # 2. Check availability (Circuit Breaker check)
        if not self._s3_available:
            logger.warning("S3 not available; using local fallback.")
            return self._use_local_storage(file_path)

        # 3. Enhanced S3 Key Generation
        if not key:
            date_str = date.today().strftime("%Y-%m-%d")
            key = f"reports/{date_str}/{file_path.name}"

        # 4. S3 Upload Logic
        try:
            self.s3_client.upload_file(
                str(file_path),
                self.bucket_name,
                key,
                # Production Security/Traceability
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

        # 5. Robust Exception Handling (Fallback logic)
        except NoCredentialsError:
            logger.error("AWS credentials missing during upload; falling back to local.")
            self._s3_available = False
            return self._use_local_storage(file_path)

        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")

            # Non-recoverable errors (Access, Config) trigger permanent fallback for the session
            if error_code in (
                "NoSuchBucket", "AccessDenied", "InvalidAccessKeyId",
                "SignatureDoesNotMatch", "403", "404"
            ):
                logger.error("Permanent S3 access error (%s); disabling S3 for session.", error_code)
                self._s3_available = False
                return self._use_local_storage(file_path)
            else:
                # Transient network or other unexpected errors
                logger.exception("S3 client error during upload (Code: %s).", error_code)
                raise

        except BotoCoreError:
            # Network-level errors (timeouts, connection issues)
            logger.exception("BotoCore network error during S3 upload; falling back to local.")
            return self._use_local_storage(file_path)

        except Exception:
            # Catch-all for unexpected issues
            logger.exception("Unexpected error during S3 upload")
            raise

    def _use_local_storage(self, file_path: Path) -> str:
        """Returns local file path with the mandatory file:// URI scheme."""
        local_path = file_path.resolve().as_posix()
        return f"file://{local_path}"

    # -------------------------------------------------------------------------
    # PUBLIC ACCESSORS/UTILITIES
    # -------------------------------------------------------------------------

    def is_s3_path(self, path: str) -> bool:
        """Checks if a path is an S3 key (True) or a local file path (False)."""
        return not path.startswith("file://")

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        """
        Generates a temporary, secure presigned URL for an S3 object.

        Returns None if S3 is unavailable or the key is a local file path.
        """
        if not self.is_s3_path(key) or not self.s3_client or not self.bucket_name:
            logger.debug("Cannot generate presigned URL (local path or S3 unavailable).")
            return None

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            logger.debug(
                "Generated presigned URL for %s (expires in %d seconds)",
                key, expires_in,
            )
            return url
        except (BotoCoreError, NoCredentialsError, ClientError) as exc:
            logger.warning("Unable to generate presigned URL for %s: %s", key, exc)
            return None

    def _get_content_type(self, file_path: Path) -> str:
        """Determines the appropriate Content-Type for the S3 upload."""
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
        """Checks S3 connectivity and bucket access. Returns True if S3 is available or using local fallback."""
        if not self.s3_client or not self.bucket_name:
            logger.info("S3 health check: using local fallback mode.")
            return True  # Local fallback is considered 'healthy' for operation flow

        # Re-run validation logic
        self._validate_credentials()
        return self._s3_available

    def list_recent_reports(
        self, prefix: str = "reports/", max_keys: int = 100
    ) -> list:
        """Lists recent reports from the S3 bucket with metadata and presigned URLs."""
        if not self.s3_client or not self.bucket_name:
            logger.info("Cannot list reports: S3 not configured or available.")
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
                            obj["Key"], expires_in=86400 # 24 hours
                        ),
                    }
                )

            logger.info("Listed %d reports from S3", len(reports))
            return reports

        except Exception as exc:
            logger.error("Failed to list reports from S3: %s", exc)
            return []