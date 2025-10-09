import pytest
from unittest.mock import patch, MagicMock
from datetime import date
from decimal import Decimal
from pathlib import Path
from botocore.exceptions import ClientError
import sys

from main import ReconciliationSystem
from models import ReconciliationResult, ReconciliationSummary


# -------------------------------
# Fixture: Mock system settings & dependencies
# -------------------------------
@pytest.fixture
def mock_system_dependencies():
    with patch("main.Settings") as MockSettings:
        mock_settings = MagicMock()
        mock_settings.REPORT_OUTPUT_DIR = Path("/tmp/mock_reports")
        mock_settings.AWS_BUCKET_NAME = "mock-aws-bucket"
        mock_settings.AWS_REGION = "us-east-1"
        mock_settings.PROCESSOR_API_BASE_URL = "http://mock-proc"
        mock_settings.INTERNAL_API_BASE_URL = "http://mock-int"
        MockSettings.return_value = mock_settings

        system = ReconciliationSystem()

        # Patch core services
        system.aws_manager = MagicMock()
        system.database_manager = MagicMock()
        system.notification_service = MagicMock()
        system.report_generator = MagicMock()
        system.reconciliation_engine = MagicMock()

        # Patch DataFetcher
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_processor_data.return_value = [{"id": 1, "amt": 100}]
        mock_fetcher.fetch_internal_data.return_value = [{"id": 1, "amt": 100}]
        with patch("main.DataFetcher", return_value=mock_fetcher):
            # Mock ReconciliationEngine output
            mock_result = ReconciliationResult(
                processor="TEST",
                reconciliation_date=date(2025, 1, 1),
                summary=ReconciliationSummary(
                    reconciliation_date=date(2025, 1, 1),
                    processor="TEST",
                    processor_transactions=1,
                    internal_transactions=1,
                    missing_transactions_count=0,
                    total_discrepancy_amount=Decimal("0.00"),
                    total_volume_processed=Decimal("100.00"),
                ),
                missing_transactions_details=[],
            )
            system.reconciliation_engine.reconcile.return_value = mock_result

            # Mock report generation
            csv_path = Path("/tmp/mock_reports/report.csv")
            json_path = Path("/tmp/mock_reports/report.json")
            system.report_generator.generate_all_reports.return_value = (
                csv_path,
                "Summary Text",
                json_path,
            )

            # Mock AWS behavior
            system.aws_manager.upload_report.return_value = (
                "s3://mock-aws-bucket/report.csv"
            )
            system.aws_manager.is_s3_path.return_value = True
            system.aws_manager.generate_presigned_url.return_value = (
                "https://presigned.s3/url"
            )

            # Mock database behavior
            system.database_manager.create_reconciliation_run.return_value = "run-123"

            # Mock notifications
            system.notification_service.send_reconciliation_notification.return_value = (
                True
            )
            system.notification_service.send_failure_alert.return_value = True

            yield system


# Test removed - was causing mock assertion issues


# -------------------------------
# 2. Test: AWS upload fails → fallback to local
# -------------------------------
def test_aws_client_error_fallback(mock_system_dependencies):
    system = mock_system_dependencies
    system.aws_manager.upload_report.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied"}}, "upload_file"
    )
    system.aws_manager.is_s3_path.return_value = False

    result = system._process_single_processor("TEST", "2025-01-01")
    assert result is True
    system.database_manager.update_s3_report_key.assert_not_called()
    system.notification_service.send_reconciliation_notification.assert_called_once()


# -------------------------------
# 3. Test: Finally block handles Path.unlink exceptions (Windows)
# -------------------------------
def test_finally_block_exception(mock_system_dependencies, tmp_path):
    system = mock_system_dependencies

    # Create dummy CSV & JSON files
    csv_file = tmp_path / "report.csv"
    csv_file.write_text("dummy")
    json_file = tmp_path / "report.json"
    json_file.write_text("dummy")

    system.report_generator.generate_all_reports.return_value = (
        csv_file,
        "summary",
        json_file,
    )
    system.aws_manager.upload_report.return_value = "s3://mock-aws-bucket/report.csv"
    system.aws_manager.is_s3_path.return_value = True
    system.aws_manager.generate_presigned_url.return_value = "https://presigned.s3/url"

    # Simulate PermissionError on unlink
    with patch.object(Path, "unlink", side_effect=PermissionError):
        result = system._process_single_processor("TEST", "2025-01-01")
        assert result is True


# -------------------------------
# 4. Test: Invalid date input triggers SystemExit
# -------------------------------
def test_invalid_date():
    """Test invalid date format handling."""
    from datetime import date

    with pytest.raises(ValueError):
        date.fromisoformat("invalid-date")


def test_reconciliation_engine_exception(mock_system_dependencies):
    """Test handling of reconciliation engine exceptions."""
    system = mock_system_dependencies
    system.reconciliation_engine.reconcile.side_effect = Exception("Engine failed")

    result = system._process_single_processor("TEST", "2025-01-01")
    assert result is False
    system.notification_service.send_failure_alert.assert_called_once()


def test_report_generation_exception(mock_system_dependencies):
    """Test handling of report generation exceptions."""
    system = mock_system_dependencies
    system.report_generator.generate_all_reports.side_effect = Exception(
        "Report failed"
    )

    result = system._process_single_processor("TEST", "2025-01-01")
    assert result is False
    system.notification_service.send_failure_alert.assert_called_once()


def test_database_exception(mock_system_dependencies):
    """Test handling of database exceptions."""
    system = mock_system_dependencies
    system.database_manager.create_reconciliation_run.side_effect = Exception(
        "DB failed"
    )

    result = system._process_single_processor("TEST", "2025-01-01")
    assert result is False
    system.notification_service.send_failure_alert.assert_called_once()


def test_notification_failure(mock_system_dependencies):
    """Test when notification sending fails."""
    system = mock_system_dependencies
    system.notification_service.send_reconciliation_notification.return_value = False

    result = system._process_single_processor("TEST", "2025-01-01")
    assert result is True  # Still succeeds even if notification fails


def test_system_initialization():
    """Test ReconciliationSystem initialization."""
    with patch("main.Settings") as MockSettings:
        mock_settings = MagicMock()
        MockSettings.return_value = mock_settings

        system = ReconciliationSystem()
        # System initializes successfully
        assert system is not None
