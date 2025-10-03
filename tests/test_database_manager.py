# tests/test_database_manager.py

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date
import uuid
from decimal import Decimal

from database_manager import DatabaseManager
from models import Transaction, ReconciliationResult, ReconciliationSummary


# -------------------------------
# Fixtures: Sample data
# -------------------------------
@pytest.fixture
def sample_transactions():
    """
    Returns a list of sample Transaction objects for testing database operations.
    """
    return [
        Transaction(
            transaction_id=str(uuid.uuid4()),
            processor_name="stripe",
            amount=Decimal("100.50"),
            currency="USD",
            merchant_id="M123",
            transaction_date=datetime.utcnow(),
            reference_number="REF001",
            fee=Decimal("1.5"),
            status="completed",
        ),
        Transaction(
            transaction_id=str(uuid.uuid4()),
            processor_name="stripe",
            amount=Decimal("200.00"),
            currency="USD",
            merchant_id="M124",
            transaction_date=datetime.utcnow(),
            reference_number="REF002",
            fee=Decimal("2.0"),
            status="completed",
        ),
    ]


@pytest.fixture
def sample_result(sample_transactions):
    """
    Returns a sample ReconciliationResult object with summary and missing transaction details.
    """
    summary = ReconciliationSummary(
        processor_transactions=2,
        internal_transactions=1,
        missing_transactions_count=1,
        total_discrepancy_amount=Decimal("100.50"),
        processor="stripe",
        reconciliation_date=datetime.utcnow().date(),
    )
    return ReconciliationResult(
        reconciliation_date=datetime.utcnow().date(),
        processor="stripe",
        summary=summary,
        missing_transactions_details=sample_transactions[:1],
    )


# -------------------------------
# Fixture: Mock DatabaseManager
# -------------------------------
@pytest.fixture
def db_manager():
    """
    Returns a DatabaseManager instance with psycopg2 connections mocked.
    All DB operations are intercepted, allowing isolated testing.
    """
    with patch("psycopg2.connect") as mock_connect, \
         patch("psycopg2.extras.execute_values") as mock_execute_values:

        # Mock connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__.return_value = mock_cursor
        mock_cursor.__exit__.return_value = None
        mock_cursor.fetchone.return_value = [str(uuid.uuid4())]
        mock_cursor.fetchall.return_value = []
        mock_cursor.rowcount = 0
        mock_cursor.connection = mock_conn

        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        yield DatabaseManager()


# -------------------------------
# Tests: DatabaseManager methods
# -------------------------------
def test_create_reconciliation_run(db_manager):
    """
    Test that creating a reconciliation run returns a non-null run ID string.
    """
    run_date = date.today()
    processor = "stripe"
    run_id = db_manager.create_reconciliation_run(run_date, processor)
    assert run_id is not None
    assert isinstance(run_id, str)


def test_update_s3_report_key(db_manager):
    """
    Test updating the S3 report key for a reconciliation run succeeds.
    """
    run_id = str(uuid.uuid4())
    key = "s3://bucket/path/to/report.csv"
    result = db_manager.update_s3_report_key(run_id, key)
    assert result is True


def test_update_reconciliation_status(db_manager):
    """
    Test updating the reconciliation status for both 'completed' and 'failed' states.
    """
    run_id = str(uuid.uuid4())
    # Completed status
    result = db_manager.update_reconciliation_status(run_id, "completed")
    assert result is True

    # Failed status with error message
    result_fail = db_manager.update_reconciliation_status(run_id, "failed", "Test error")
    assert result_fail is True


def test_health_check(db_manager):
    """
    Test that health_check returns True when database connection is mocked.
    """
    assert db_manager.health_check() is True


def test_get_reconciliation_history(db_manager):
    """
    Test retrieving reconciliation history returns a list.
    Mocked fetchall returns empty list.
    """
    history = db_manager.get_reconciliation_history("stripe", days=7)
    assert isinstance(history, list)
    assert history == []  # empty due to mocked fetchall
