# tests/test_aws_manager.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys
from botocore.exceptions import BotoCoreError

# Add src to sys.path so Python can find it
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aws_manager import AWSManager


# -------------------------------
# Fixtures
# -------------------------------
@pytest.fixture
def tmp_report_file(tmp_path) -> Path:
    """Create a temporary dummy CSV report for upload tests."""
    file = tmp_path / "dummy_report.csv"
    file.write_text("id,name\n1,Test")
    return file


# -------------------------------
# Happy path tests
# -------------------------------
def test_s3_upload_success(tmp_report_file):
    """
    Validate that upload_report returns the correct S3 key when S3 is available.
    """
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.head_bucket.return_value = {}  # Simulate bucket exists
        mock_client.upload_file.return_value = None

        manager = AWSManager(bucket_name="dummy-bucket")
        manager.s3_client = mock_client
        manager._s3_available = True

        key = manager.upload_report(tmp_report_file)
        assert key.startswith("reports/")


def test_generate_presigned_url(tmp_report_file):
    """
    Validate that generate_presigned_url returns a correct URL for an S3 object.
    """
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.head_bucket.return_value = {}
        mock_client.upload_file.return_value = None
        mock_client.generate_presigned_url.return_value = "http://example.com/presigned"

        manager = AWSManager(bucket_name="dummy-bucket")
        manager.s3_client = mock_client
        manager._s3_available = True

        key = manager.upload_report(tmp_report_file)
        url = manager.generate_presigned_url(key)
        assert url == "http://example.com/presigned"


def test_list_recent_reports():
    """
    Validate that list_recent_reports returns recent S3 objects with presigned URLs.
    """
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client

        mock_client.head_bucket.return_value = {}
        mock_client.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "reports/2025-10-03/file.csv",
                    "Size": 123,
                    "LastModified": MagicMock(isoformat=lambda: "2025-10-03T00:00:00"),
                }
            ]
        }
        mock_client.generate_presigned_url.return_value = "http://example.com/presigned"

        manager = AWSManager(bucket_name="dummy-bucket")
        manager.s3_client = mock_client
        manager._s3_available = True

        reports = manager.list_recent_reports()
        assert len(reports) == 1
        assert reports[0]["key"] == "reports/2025-10-03/file.csv"
        assert reports[0]["presigned_url"] == "http://example.com/presigned"


# -------------------------------
# Fallback & edge case tests
# -------------------------------



def test_upload_report_file_not_found():
    """
    Uploading a non-existent file should raise FileNotFoundError.
    """
    manager = AWSManager(bucket_name=None)
    fake_file = Path("/nonexistent/file.csv")
    with pytest.raises(FileNotFoundError):
        manager.upload_report(fake_file)


def test_upload_report_client_error_fallback(tmp_report_file):
    """
    If upload to S3 fails, an exception should be propagated.
    """
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.upload_file.side_effect = Exception("Test error")

        manager = AWSManager(bucket_name="dummy-bucket")
        manager.s3_client = mock_client
        manager._s3_available = True

        with pytest.raises(Exception, match="Test error"):
            manager.upload_report(tmp_report_file)


def test_generate_presigned_url_local(tmp_report_file):
    """
    Presigned URL generation for local storage should return None.
    """
    manager = AWSManager(bucket_name=None)
    path = manager._use_local_storage(tmp_report_file)
    url = manager.generate_presigned_url(path)
    assert url is None





def test_health_check_fallback(monkeypatch):
    """
    Health check returns True when S3 client is not configured.
    """
    manager = AWSManager(bucket_name=None)
    assert manager.health_check() is True


def test_validate_credentials_client_error(monkeypatch):
    """
    Validate that _validate_credentials handles ClientError properly and disables S3.
    """
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        from botocore.exceptions import ClientError

        # Simulate access denied
        error_response = {"Error": {"Code": "AccessDenied"}}
        mock_client.head_bucket.side_effect = ClientError(error_response, "HeadBucket")

        manager = AWSManager(bucket_name="dummy-bucket")
        manager.s3_client = mock_client
        manager._validate_credentials()

        assert manager._s3_available is False
        assert manager.s3_client is None


def test_upload_report_botocore_error_fallback(tmp_report_file):
    """Simulate BotoCoreError during upload; should fall back to local storage."""
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.upload_file.side_effect = BotoCoreError()

        manager = AWSManager(bucket_name="dummy-bucket")
        manager.s3_client = mock_client
        manager._s3_available = True

        path = manager.upload_report(tmp_report_file)
        assert path.startswith("file://")


def test_upload_report_unexpected_exception(tmp_report_file):
    """Simulate unexpected exception; should raise."""
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.upload_file.side_effect = RuntimeError("Unexpected")

        manager = AWSManager(bucket_name="dummy-bucket")
        manager.s3_client = mock_client
        manager._s3_available = True

        with pytest.raises(RuntimeError, match="Unexpected"):
            manager.upload_report(tmp_report_file)


def test_get_content_type_default(tmp_path):
    """Ensure unknown file extensions return 'application/octet-stream'."""
    file = tmp_path / "weird_file.unknown"
    file.write_text("dummy")
    manager = AWSManager()
    ctype = manager._get_content_type(file)
    assert ctype == "application/octet-stream"
