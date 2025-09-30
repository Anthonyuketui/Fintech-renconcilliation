"""Handles report storage in AWS S3 or a local fallback."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional
from datetime import date

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
            key: Optional object key to use in S3.  If omitted, creates
                organized path with date and filename.

        Returns:
            If uploaded to S3, returns the S3 object key.  Otherwise returns
            the absolute path of the local file.
        """
        if not self.s3_client or not self.bucket_name:
            # Simply return path; caller may treat this as local storage
            return str(file_path.resolve())
        
        # Enhanced key generation with date organization for production
        if not key:
            date_str = date.today().strftime('%Y-%m-%d')
            key = f"reports/{date_str}/{file_path.name}"
        
        try:
            # Upload with metadata and encryption for production security
            self.s3_client.upload_file(
                str(file_path), 
                self.bucket_name, 
                key,
                ExtraArgs={
                    'Metadata': {
                        'upload_date': date.today().isoformat(),
                        'system': 'fintech_reconciliation',
                        'file_type': file_path.suffix.lstrip('.') or 'unknown'
                    },
                    'ServerSideEncryption': 'AES256',  # Encrypt at rest
                    'ContentType': self._get_content_type(file_path)
                }
            )
            logger.info("Uploaded report to S3 bucket %s as %s", self.bucket_name, key)
            return key
        except (BotoCoreError, NoCredentialsError) as exc:
            logger.exception("Failed to upload to S3, falling back to local storage: %s", exc)
            return str(file_path.resolve())

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        """Generate a presigned URL for an S3 object if possible.

        Args:
            key: The object key in the configured bucket.
            expires_in: Expiration time in seconds (default: 1 hour).

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
            logger.debug("Generated presigned URL for %s (expires in %d seconds)", key, expires_in)
            return url
        except (BotoCoreError, NoCredentialsError) as exc:
            logger.warning("Unable to generate presigned URL: %s", exc)
            return None

    def _get_content_type(self, file_path: Path) -> str:
        """Determine appropriate content type based on file extension."""
        suffix = file_path.suffix.lower()
        content_types = {
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.txt': 'text/plain',
            '.pdf': 'application/pdf',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }
        return content_types.get(suffix, 'application/octet-stream')

    def health_check(self) -> bool:
        """Check S3 connectivity and bucket access."""
        if not self.s3_client or not self.bucket_name:
            logger.info("S3 health check: using local fallback mode")
            return True  # Local fallback is healthy
        
        try:
            # Test bucket access
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info("S3 health check passed for bucket: %s", self.bucket_name)
            return True
        except Exception as exc:
            logger.error("S3 health check failed: %s", exc)
            return False

    def list_recent_reports(self, prefix: str = "reports/", max_keys: int = 100) -> list:
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
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            reports = []
            for obj in response.get('Contents', []):
                reports.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat(),
                    'presigned_url': self.generate_presigned_url(obj['Key'], expires_in=86400)  # 24 hours
                })
            
            logger.info("Listed %d reports from S3", len(reports))
            return reports
            
        except Exception as exc:
            logger.error("Failed to list reports from S3: %s", exc)
            return []