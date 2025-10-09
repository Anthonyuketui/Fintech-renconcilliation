# tests/test_models.py

import pytest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from unittest.mock import patch
from models import (
    Settings,
    Transaction,
    ReconciliationSummary,
    ReconciliationResult,
    ReportBundle,
    ReconciliationRun,
    AuditLog,
)


# -------------------------------
# Settings Tests
# -------------------------------



def test_settings_database_url():
    """Test database URL construction."""
    settings = Settings(
        DB_USER="test_user",
        DB_PASSWORD="test_password",
        DB_HOST="test_host",
        DB_PORT=5433,
        DB_NAME="test_db",
    )
    expected = "postgresql://test_user:test_password@test_host:5433/test_db"
    assert settings.database_url == expected


def test_settings_database_url_override():
    """Test DB_URL override."""
    settings = Settings(DB_URL="postgresql://override:url@host:5432/db")
    assert settings.database_url == "postgresql://override:url@host:5432/db"


def test_settings_s3_bucket_name():
    """Test S3 bucket name property."""
    settings = Settings(AWS_S3_BUCKET_NAME="bucket1", AWS_BUCKET_NAME="bucket2")
    assert settings.s3_bucket_name == "bucket1"

    # Test with only AWS_BUCKET_NAME set
    settings = Settings(AWS_BUCKET_NAME="bucket2", AWS_S3_BUCKET_NAME=None)
    assert settings.s3_bucket_name == "bucket2"


# -------------------------------
# Transaction Tests
# -------------------------------
def test_transaction_creation():
    """Test Transaction model creation."""
    transaction = Transaction(
        transaction_id="TXN_001",
        processor_name="stripe",
        amount=Decimal("100.50"),
        currency="USD",
        status="completed",
        merchant_id="MERCH_001",
        transaction_date=datetime.utcnow(),
        reference_number="REF_001",
        fee=Decimal("2.50"),
    )
    assert transaction.transaction_id == "TXN_001"
    assert transaction.amount == Decimal("100.50")


# -------------------------------
# ReconciliationSummary Tests
# -------------------------------
def test_reconciliation_summary():
    """Test ReconciliationSummary model."""
    summary = ReconciliationSummary(
        reconciliation_date=date.today(),
        processor="stripe",
        processor_transactions=100,
        internal_transactions=95,
        missing_transactions_count=5,
        total_discrepancy_amount=Decimal("500.00"),
        total_volume_processed=Decimal("10000.00"),
    )
    assert summary.missing_transactions_count == 5
    assert summary.total_discrepancy_amount == Decimal("500.00")


def test_reconciliation_summary_defaults():
    """Test ReconciliationSummary with default values."""
    summary = ReconciliationSummary(
        reconciliation_date=date.today(),
        processor="stripe",
        processor_transactions=100,
        internal_transactions=95,
        missing_transactions_count=5,
    )
    assert summary.total_discrepancy_amount == Decimal("0.00")
    assert summary.total_volume_processed == Decimal("0.00")


# -------------------------------
# ReconciliationResult Tests
# -------------------------------
def test_reconciliation_result():
    """Test ReconciliationResult model."""
    summary = ReconciliationSummary(
        reconciliation_date=date.today(),
        processor="stripe",
        processor_transactions=100,
        internal_transactions=95,
        missing_transactions_count=5,
    )

    result = ReconciliationResult(
        reconciliation_date=date.today(),
        processor="stripe",
        summary=summary,
        missing_transactions_details=[],
    )
    assert result.processor == "stripe"
    assert len(result.missing_transactions_details) == 0


# -------------------------------
# ReportBundle Tests
# -------------------------------
def test_report_bundle():
    """Test ReportBundle model."""
    bundle = ReportBundle(
        csv_path=Path("report.csv"),
        json_path=Path("report.json"),
        summary_text="Test summary",
    )
    assert bundle.csv_path == Path("report.csv")
    assert bundle.summary_text == "Test summary"


# -------------------------------
# ReconciliationRun Tests
# -------------------------------
def test_reconciliation_run():
    """Test ReconciliationRun model."""
    run = ReconciliationRun(
        id="uuid-123",
        run_date=date.today(),
        processor_name="stripe",
        start_time=datetime.utcnow(),
        status="running",
        created_by="system",
    )
    assert run.id == "uuid-123"
    assert run.status == "running"


def test_reconciliation_run_with_error():
    """Test ReconciliationRun with error message."""
    run = ReconciliationRun(
        id="uuid-123",
        run_date=date.today(),
        processor_name="stripe",
        start_time=datetime.utcnow(),
        status="failed",
        created_by="system",
        error_message="Connection timeout",
    )
    assert run.error_message == "Connection timeout"


# -------------------------------
# AuditLog Tests
# -------------------------------
def test_audit_log():
    """Test AuditLog model."""
    log = AuditLog(
        id="audit-123",
        action="reconciliation_started",
        table_name="reconciliation_runs",
        record_id="run-123",
        user_id="system",
        application_name="fintech-reconciliation",
    )
    assert log.action == "reconciliation_started"
    assert log.table_name == "reconciliation_runs"


def test_audit_log_with_values():
    """Test AuditLog with old/new values."""
    log = AuditLog(
        id="audit-123",
        action="status_update",
        table_name="reconciliation_runs",
        record_id="run-123",
        old_values={"status": "running"},
        new_values={"status": "completed"},
        user_id="system",
        application_name="fintech-reconciliation",
    )
    assert log.old_values == {"status": "running"}
    assert log.new_values == {"status": "completed"}


def test_audit_log_timestamp_default():
    """Test AuditLog timestamp default."""
    log = AuditLog(
        id="audit-123",
        action="test",
        table_name="test",
        record_id="test",
        user_id="test",
        application_name="test",
    )
    assert isinstance(log.timestamp, datetime)
