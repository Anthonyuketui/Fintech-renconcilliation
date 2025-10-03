# tests/test_main.py

import pytest
from unittest.mock import patch, MagicMock
from datetime import date
from decimal import Decimal
from pathlib import Path

from main import ReconciliationSystem
from models import ReconciliationResult, ReconciliationSummary

# -------------------------------
# Fixture to mock Settings & system dependencies
# -------------------------------
@pytest.fixture
def mock_system_dependencies():
    with patch("main.Settings") as MockSettings:
        # Mock Settings object
        mock_settings = MagicMock()
        mock_settings.REPORT_OUTPUT_DIR = Path("/tmp/mock_reports")
        mock_settings.AWS_BUCKET_NAME = "mock-aws-bucket"
        mock_settings.AWS_REGION = "us-east-1"
        mock_settings.PROCESSOR_API_BASE_URL = "http://mock-proc"
        mock_settings.INTERNAL_API_BASE_URL = "http://mock-int"
        MockSettings.return_value = mock_settings

        # Initialize ReconciliationSystem
        system = ReconciliationSystem()

        # Patch service dependencies
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

            # Mock reports
            csv_path = Path("/tmp/mock_reports/report.csv")
            json_path = Path("/tmp/mock_reports/report.json")
            system.report_generator.generate_all_reports.return_value = (
                csv_path,
                "Summary Text",
                json_path,
            )

            # AWS mocks
            system.aws_manager.upload_report.return_value = "s3://mock-aws-bucket/report.csv"
            system.aws_manager.is_s3_path.return_value = True
            system.aws_manager.generate_presigned_url.return_value = "https://presigned.s3/url"

            # Database mocks
            system.database_manager.create_reconciliation_run.return_value = "run-123"

            # Notification mocks
            system.notification_service.send_reconciliation_notification.return_value = True
            system.notification_service.send_failure_alert.return_value = True

            yield system

# -------------------------------
# 1. Test: Successful run with S3 upload
# -------------------------------
def test_successful_run_with_s3(mock_system_dependencies):
    system = mock_system_dependencies
    result = system._process_single_processor("TEST", "2025-01-01")

    assert result is True
    system.database_manager.create_reconciliation_run.assert_called_once()
    system.reconciliation_engine.reconcile.assert_called_once()
    system.report_generator.generate_all_reports.assert_called_once()
    system.aws_manager.upload_report.assert_called_once()
    system.aws_manager.generate_presigned_url.assert_called_once()
    system.notification_service.send_reconciliation_notification.assert_called_once()

# -------------------------------
# 2. Test: Successful
