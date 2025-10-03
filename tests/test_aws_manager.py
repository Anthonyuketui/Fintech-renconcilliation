import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

# Add src to sys.path so Python can find it
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aws_manager import AWSManager


@pytest.fixture
def tmp_report_file(tmp_path) -> Path:
    """Create a temporary dummy CSV report."""
    file = tmp_path / "dummy_report.csv"
    file.write_text("id,name\n1,Test")
    return file


def test_s3_upload_success(tmp_report_file):
    """Test that upload_report returns the correct S3 key."""
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.head_bucket.return_value = {}       # Pretend bucket exists
        mock_client.upload_file.return_value = None     # Pretend upload works

        manager = AWSManager(bucket_name="dummy-bucket")
        manager.s3_client = mock_client
        manager._s3_available = True  # Force S3 mode

        key = manager.upload_report(tmp_report_file)
        assert key.startswith("reports/")                # Now should pass


def test_generate_presigned_url(tmp_report_file):
    """Test presigned URL generation."""
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.head_bucket.return_value = {}
        mock_client.upload_file.return_value = None
        mock_client.generate_presigned_url.return_value = "http://example.com/presigned"

        manager = AWSManager(bucket_name="dummy-bucket")
        manager.s3_client = mock_client
        manager._s3_available = True  # Force S3 mode

        key = manager.upload_report(tmp_report_file)
        url = manager.generate_presigned_url(key)
        assert url == "http://example.com/presigned"


def test_list_recent_reports():
    """Test listing of recent reports."""
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client

        mock_client.head_bucket.return_value = {}
        mock_client.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "reports/2025-10-03/file.csv",
                    "Size": 123,
                    "LastModified": MagicMock(isoformat=lambda: "2025-10-03T00:00:00")
                }
            ]
        }
        mock_client.generate_presigned_url.return_value = "http://example.com/presigned"

        manager = AWSManager(bucket_name="dummy-bucket")
        manager.s3_client = mock_client
        manager._s3_available = True  # Force S3 mode

        reports = manager.list_recent_reports()
        assert len(reports) == 1
        assert reports[0]["key"] == "reports/2025-10-03/file.csv"
        assert reports[0]["presigned_url"] == "http://example.com/presigned"
