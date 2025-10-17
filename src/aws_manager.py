"""
aws_manager.py

## AWS S3 Storage Manager with Local Fallback

This module provides the AWSManager class for handling report persistence.
It prioritizes secure, permanent storage in AWS S3 but implements a reliable
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

# Constants for S3 error handling
PERMANENT_S3_ERRORS = frozenset({
    "NoSuchBucket", "AccessDenied", "InvalidAccessKeyId",
    "SignatureDoesNotMatch", "403", "404"
})


class AWSManager:
    """
    Manages report storage, defaulting to S3 and falling back to local files.

    Returns the S3 object key or a local "file://" prefixed path, allowing
    the caller to transparently handle either storage location.
    """

    def __init__(self, bucket_name: Optional[str] = None, region: Optional[str] = None) -> None:
        """Initializes S3 configuration and client, validating access immediately."""
        self.bucket_name = bucket_name or os.getenv("AWS_S3_BUCKET_NAME")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.s3_client = None
        self._s3_available = False

        self._initialize_s3_client()

    def _initialize_s3_client(self) -> None:
        """Initializes and validates the S3 client, setting _s3_available."""
        if not self.bucket_name:
            logger.info("AWS S3 bucket name not configured; using local fallback.")
            return

        try:
            self.s3_client = boto3.client("s3", region_name=self.region)
            self._validate_credentials()

        except (BotoCoreError, ClientError, NoCredentialsError) as exc:
            logger.warning("Failed to initialize S3 client: %s. Using local fallback.", exc)
            self.s3_client = None
            self._s3_available = False
        except Exception as exc:
            logger.error("Unexpected error initializing S3 client: %s. Using local fallback.", exc)
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
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            self._s3_available = True
            logger.info("AWS S3 validated successfully for bucket: %s", self.bucket_name)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            logger.warning("AWS credentials invalid or bucket inaccessible (%s). Falling back to local.", error_code)
            self._s3_available = False
            self.s3_client = None
        except Exception as exc:
            logger.warning("Failed to validate S3 access: %s. Falling back to local.", exc)
            self._s3_available = False
            self.s3_client = None

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
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not self._s3_available:
            logger.warning("S3 not available; using local fallback.")
            return self._use_local_storage(file_path)

        if not key:
            date_str = date.today().strftime("%Y-%m-%d")
            safe_name = file_path.name
            if ".." in safe_name or "/" in safe_name or "\\" in safe_name:
                safe_name = Path(safe_name).name
            key = f"reports/{date_str}/{safe_name}"
            
        extra_args = {
            "Metadata": {
                "upload_date": date.today().isoformat(),
                "system": "fintech_reconciliation",
                "file_type": file_path.suffix.lstrip(".") or "unknown",
            },
            "ServerSideEncryption": "AES256",
            "ContentType": self._get_content_type(file_path),
        }
        
        try:
            self.s3_client.upload_file(str(file_path), self.bucket_name, key, ExtraArgs=extra_args)
            logger.info("Uploaded %s to S3 bucket %s", key, self.bucket_name)
            return key
        except Exception as exc:
            return self._handle_s3_upload_exception(exc, file_path)

    def _handle_s3_upload_exception(self, exc: Exception, file_path: Path) -> str:
        """Handles exceptions during S3 upload and applies fallback logic."""
        if isinstance(exc, NoCredentialsError):
            logger.error("AWS credentials missing during upload; falling back to local.")
            self._s3_available = False
            return self._use_local_storage(file_path)
        elif isinstance(exc, ClientError):
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            if error_code in PERMANENT_S3_ERRORS:
                logger.error("Permanent S3 access error (%s); disabling S3.", error_code)
                self._s3_available = False
                return self._use_local_storage(file_path)
            else:
                logger.exception("S3 client error during upload: %s", error_code)
                raise
        elif isinstance(exc, BotoCoreError):
            logger.exception("Network error during S3 upload; using local fallback")
            return self._use_local_storage(file_path)
        else:
            logger.exception("Unexpected S3 upload error: %s", exc)
            raise

    def _use_local_storage(self, file_path: Path) -> str:
        """Returns local file path with the mandatory file:// URI scheme."""
        # Normalize and validate path to prevent traversal
        normalized_path = os.path.normpath(str(file_path))
        if ".." in normalized_path or normalized_path.startswith("/"):
            # Only allow relative paths in safe directories
            safe_name = os.path.basename(normalized_path)
            reports_dir = Path("./reports")
            reports_dir.mkdir(exist_ok=True)
            safe_path = reports_dir / safe_name
        else:
            safe_path = Path(normalized_path)
            
        resolved_path = safe_path.resolve()
        return f"file://{resolved_path.as_posix()}"

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
            logger.debug("Generated presigned URL for %s (expires in %d seconds)", key, expires_in)
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
        """Checks S3 connectivity. Returns True if available or using local fallback."""
        if not self.s3_client or not self.bucket_name:
            logger.info("S3 health check: using local fallback mode.")
            return True

        self._validate_credentials()
        return self._s3_available

    def list_recent_reports(self, prefix: str = "reports/", max_keys: int = 100) -> list:
        """
        Lists recent reports from the S3 bucket with metadata and presigned URLs.
        
        Args:
            prefix: S3 key prefix to filter reports
            max_keys: Maximum number of reports to return
            
        Returns:
            List of report dictionaries with keys, sizes, and presigned URLs
        """
        if not self.s3_client or not self.bucket_name:
            logger.info("Cannot list reports: S3 not configured or available.")
            return []

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=prefix, MaxKeys=max_keys
            )

            reports = []
            for obj in response.get("Contents", []):
                reports.append({
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                    "presigned_url": self.generate_presigned_url(obj["Key"], expires_in=86400),
                })

            logger.info("Listed %d reports from S3", len(reports))
            return reports

        except Exception as exc:
            logger.error("Failed to list reports from S3: %s", exc)
            return []