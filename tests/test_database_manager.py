# tests/test_database_manager.py
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date
import uuid
from decimal import Decimal

from database_manager import DatabaseManager
from models import Transaction, ReconciliationResult, ReconciliationSummary

# -----------------------------
# Fixtures: sample transactions and reconciliation results
# -----------------------------
@pytest.fixture
def sample_transactions():
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
            status="completed"
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
            status="completed"
        )
    ]


@pytest.fixture
def sample_result(sample_transactions):
    summary = ReconciliationSummary(
        processor="stripe",
        reconciliation_date=datetime.utcnow().date(),
        processor_transactions=2,
        internal_transactions=1,
        missing_transactions_count=1,
        total_discrepancy_amount=Decimal("100.50")
    )
    return ReconciliationResult(
        reconciliation_date=datetime.utcnow().date(),
        processor="stripe",
        summary=summary,
        missing_transactions_details=sample_transactions[:1]
    )

# -----------------------------
# Mock DatabaseManager
# -----------------------------
@pytest.fixture
def db_manager():
    with patch("psycopg2.connect") as mock_connect:
        # Mock the connection object
        mock_conn = MagicMock()
        
        # Mock the cursor object
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0
        mock_cursor.fetchone.return_value = [str(uuid.uuid4())]
        mock_cursor.fetchall.return_value = []
        
        # FIX: Mock the connection attribute on the cursor (needed for store_reconciliation_result)
        mock_cursor.connection.encoding = "utf-8"
        
        # Ensure cursor context manager works
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Patch psycopg2.connect to return the mock connection
        mock_connect.return_value = mock_conn
        
        # Yield the DatabaseManager instance with mocked connection
        yield DatabaseManager()

# -----------------------------
# Patch execute_values globally
# -----------------------------
@pytest.fixture(autouse=True)
def patch_execute_values():
    with patch("psycopg2.extras.execute_values") as mock_exec_values:
        yield mock_exec_values

# -----------------------------
# Tests for DatabaseManager
# -----------------------------
def test_create_reconciliation_run(db_manager):
    run_date = date.today()
    processor = "stripe"
    run_id = db_manager.create_reconciliation_run(run_date, processor)
    assert run_id is not None
    assert isinstance(run_id, str)


def test_store_reconciliation_result(db_manager, sample_result):
    run_id = str(uuid.uuid4())
    # Should not raise exceptions
    db_manager.store_reconciliation_result(run_id, sample_result)


def test_update_s3_report_key(db_manager):
    run_id = str(uuid.uuid4())
    key = "s3://bucket/path/to/report.csv"
    result = db_manager.update_s3_report_key(run_id, key)
    assert result is True


def test_update_reconciliation_status(db_manager):
    run_id = str(uuid.uuid4())
    result = db_manager.update_reconciliation_status(run_id, "completed")
    assert result is True
    result_fail = db_manager.update_reconciliation_status(run_id, "failed", "Test error")
    assert result_fail is True


def test_health_check(db_manager):
    # Should return True because connection is mocked
    assert db_manager.health_check() is True


def test_get_reconciliation_history(db_manager):
    history = db_manager.get_reconciliation_history("stripe", days=7)
    assert isinstance(history, list)
    assert history == []  # mocked fetchall returns empty list
