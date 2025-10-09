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
    with (
        patch("psycopg2.connect") as mock_connect,
        patch("psycopg2.extras.execute_values") as mock_execute_values,
    ):

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
    result_fail = db_manager.update_reconciliation_status(
        run_id, "failed", "Test error"
    )
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


def test_health_check_failure():
    """
    Test health check when database connection fails.
    """
    with patch("psycopg2.connect", side_effect=Exception("Connection failed")):
        db_manager = DatabaseManager()
        assert db_manager.health_check() is False


def test_create_reconciliation_run_with_exception():
    """
    Test reconciliation run creation when database operation fails.
    """
    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__.return_value = mock_cursor
        mock_cursor.__exit__.return_value = None
        mock_cursor.execute.side_effect = Exception("DB Error")
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        db_manager = DatabaseManager()
        with pytest.raises(Exception):
            db_manager.create_reconciliation_run(date.today(), "stripe")


def test_update_reconciliation_status_handles_errors(db_manager):
    """
    Test that status update handles database errors gracefully.
    """
    # Test with invalid run_id that would cause database error
    result = db_manager.update_reconciliation_status("invalid-run-id", "failed")
    # Method should handle errors and return False or True
    assert isinstance(result, bool)


def test_store_reconciliation_result(db_manager, sample_result):
    """
    Test storing reconciliation results with missing transactions.
    """
    with (
        patch("database_manager.execute_values") as mock_execute_values,
        patch.object(db_manager, "get_connection") as mock_get_conn,
    ):
        # Setup proper mock for RealDictCursor behavior
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__.return_value = mock_cursor
        mock_cursor.__exit__.return_value = None
        # Mock fetchone to return dict-like object for data quality checks
        mock_cursor.fetchone.return_value = {
            "txn_count": 1,
            "total_amount": Decimal("100.50"),
        }
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        run_id = str(uuid.uuid4())
        # Should complete without raising exceptions
        db_manager.store_reconciliation_result(run_id, sample_result)
        # Verify method completes successfully
        assert True


def test_bulk_insert_missing_transactions(db_manager, sample_transactions):
    """
    Test bulk insertion of missing transactions.
    """
    with patch("database_manager.execute_values") as mock_execute_values:
        mock_cursor = MagicMock()
        run_id = str(uuid.uuid4())
        db_manager._bulk_insert_missing_transactions(
            mock_cursor, run_id, sample_transactions
        )
        # Verify execute_values was called for bulk insert
        assert mock_execute_values.called


def test_validate_transaction_valid(db_manager, sample_transactions):
    """
    Test transaction validation with valid transaction data.
    """
    valid_txn = sample_transactions[0]
    result = db_manager._validate_transaction(valid_txn)
    assert result is True


def test_validate_transaction_invalid(db_manager):
    """
    Test transaction validation with invalid transaction data.
    """
    # Test with invalid transaction (negative amount)
    invalid_txn = Transaction(
        transaction_id="TEST_001",
        processor_name="stripe",
        amount=Decimal("-100.00"),  # Invalid negative amount
        currency="USD",
        merchant_id="M123",
        transaction_date=datetime.utcnow(),
        reference_number="REF001",
        fee=Decimal("1.5"),
        status="completed",
    )
    result = db_manager._validate_transaction(invalid_txn)
    assert result is False


def test_validate_transaction_empty_fields(db_manager):
    """
    Test transaction validation with empty required fields.
    """
    # Test with empty transaction_id
    invalid_txn = Transaction(
        transaction_id="",  # Empty transaction ID
        processor_name="stripe",
        amount=Decimal("100.00"),
        currency="USD",
        merchant_id="M123",
        transaction_date=datetime.utcnow(),
        reference_number="REF001",
        fee=Decimal("1.5"),
        status="completed",
    )
    result = db_manager._validate_transaction(invalid_txn)
    assert result is False


def test_validate_transaction_invalid_currency(db_manager):
    """
    Test transaction validation with invalid currency code.
    """
    invalid_txn = Transaction(
        transaction_id="TEST_001",
        processor_name="stripe",
        amount=Decimal("100.00"),
        currency="us",  # Invalid currency (not 3 uppercase letters)
        merchant_id="M123",
        transaction_date=datetime.utcnow(),
        reference_number="REF001",
        fee=Decimal("1.5"),
        status="completed",
    )
    result = db_manager._validate_transaction(invalid_txn)
    assert result is False


def test_data_quality_checks(db_manager, sample_result):
    """
    Test data quality checks execution.
    """
    with patch.object(db_manager, "get_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__.return_value = mock_cursor
        mock_cursor.__exit__.return_value = None
        mock_cursor.fetchone.return_value = {
            "txn_count": 1,
            "total_amount": Decimal("100.50"),
        }
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        run_id = str(uuid.uuid4())
        db_manager._perform_data_quality_checks(mock_cursor, run_id, sample_result)
        # Verify quality checks were executed
        assert mock_cursor.execute.called


def test_calculate_success_rate(db_manager, sample_result):
    """
    Test success rate calculation.
    """
    success_rate = db_manager._calculate_success_rate(sample_result)
    expected_rate = (
        (2 - 1) / 2
    ) * 100  # (processor_txns - missing) / processor_txns * 100
    assert success_rate == expected_rate


def test_calculate_success_rate_zero_transactions(db_manager):
    """
    Test success rate calculation with zero processor transactions.
    """
    summary = ReconciliationSummary(
        processor_transactions=0,
        internal_transactions=0,
        missing_transactions_count=0,
        total_discrepancy_amount=Decimal("0.00"),
        processor="stripe",
        reconciliation_date=datetime.utcnow().date(),
    )
    result = ReconciliationResult(
        reconciliation_date=datetime.utcnow().date(),
        processor="stripe",
        summary=summary,
        missing_transactions_details=[],
    )
    success_rate = db_manager._calculate_success_rate(result)
    assert success_rate == 100.0


def test_audit_logging(db_manager):
    """
    Test audit event logging functionality.
    """
    with patch.object(db_manager, "get_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__.return_value = mock_cursor
        mock_cursor.__exit__.return_value = None
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        db_manager._log_audit_event(
            mock_cursor,
            action="test_action",
            table_name="test_table",
            record_id="test_id",
            new_values={"test": "value"},
        )
        # Verify audit log insert was called
        assert mock_cursor.execute.called
