"""
Unit tests for ReconciliationEngine

Covers core business logic: transaction comparison, discrepancy detection,
financial calculations, and large dataset performance.
"""

import sys
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal
import time

import pytest

# Ensure src modules are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import ReconciliationResult, Transaction
from reconciliation_engine import ReconciliationEngine


# -------------------------------
# TEST SUITE
# -------------------------------
class TestReconciliationEngine:
    """Test suite for ReconciliationEngine class"""

    # ---------------------------
    # Fixtures
    # ---------------------------
    @pytest.fixture
    def engine(self):
        """Return a ReconciliationEngine instance for testing."""
        return ReconciliationEngine()

    @pytest.fixture
    def sample_processor_transactions(self):
        """Sample processor transactions for testing."""
        return [
            Transaction(
                transaction_id="TXN_STRIPE_20250930_0001",
                processor_name="stripe",
                amount=Decimal("100.00"),
                currency="USD",
                status="completed",
                merchant_id="MERCH_001",
                transaction_date=datetime(2025, 9, 30, 10, 0, 0),
                reference_number="REF_001",
                fee=Decimal("3.20"),
            ),
            Transaction(
                transaction_id="TXN_STRIPE_20250930_0002",
                processor_name="stripe",
                amount=Decimal("250.50"),
                currency="USD",
                status="completed",
                merchant_id="MERCH_002",
                transaction_date=datetime(2025, 9, 30, 11, 0, 0),
                reference_number="REF_002",
                fee=Decimal("7.56"),
            ),
            Transaction(
                transaction_id="TXN_STRIPE_20250930_0003",
                processor_name="stripe",
                amount=Decimal("50.00"),
                currency="USD",
                status="completed",
                merchant_id="MERCH_003",
                transaction_date=datetime(2025, 9, 30, 12, 0, 0),
                reference_number="REF_003",
                fee=Decimal("1.75"),
            ),
        ]

    @pytest.fixture
    def sample_internal_transactions(self):
        """Sample internal transactions (one transaction missing)."""
        return [
            Transaction(
                transaction_id="TXN_STRIPE_20250930_0001",
                processor_name="stripe",
                amount=Decimal("100.00"),
                currency="USD",
                status="completed",
                merchant_id="MERCH_001",
                transaction_date=datetime(2025, 9, 30, 10, 0, 0),
                reference_number="REF_001",
                fee=Decimal("3.20"),
            ),
            Transaction(
                transaction_id="TXN_STRIPE_20250930_0003",
                processor_name="stripe",
                amount=Decimal("50.00"),
                currency="USD",
                status="completed",
                merchant_id="MERCH_003",
                transaction_date=datetime(2025, 9, 30, 12, 0, 0),
                reference_number="REF_003",
                fee=Decimal("1.75"),
            ),
        ]

    # ---------------------------
    # Core Reconciliation Tests
    # ---------------------------
    def test_reconcile_identifies_missing_transactions(
        self, engine, sample_processor_transactions, sample_internal_transactions
    ):
        """Reconciliation should identify missing transactions correctly."""
        result = engine.reconcile(
            sample_processor_transactions,
            sample_internal_transactions,
            date(2025, 9, 30),
            "stripe",
        )

        assert result.summary.missing_transactions_count == 1
        assert len(result.missing_transactions_details) == 1
        assert result.missing_transactions_details[0].transaction_id == "TXN_STRIPE_20250930_0002"

    def test_reconcile_calculates_discrepancy_amount(
        self, engine, sample_processor_transactions, sample_internal_transactions
    ):
        """Total discrepancy amount should equal sum of missing transactions."""
        result = engine.reconcile(
            sample_processor_transactions,
            sample_internal_transactions,
            date(2025, 9, 30),
            "stripe",
        )
        expected_discrepancy = Decimal("250.50")
        assert result.summary.total_discrepancy_amount == expected_discrepancy

    def test_reconcile_calculates_total_volume(
        self, engine, sample_processor_transactions, sample_internal_transactions
    ):
        """Total volume processed should include all processor transactions."""
        result = engine.reconcile(
            sample_processor_transactions,
            sample_internal_transactions,
            date(2025, 9, 30),
            "stripe",
        )
        expected_volume = Decimal("100.00") + Decimal("250.50") + Decimal("50.00")
        assert result.summary.total_volume_processed == expected_volume

    def test_reconcile_perfect_match(self, engine, sample_processor_transactions):
        """No discrepancies when processor and internal transactions match perfectly."""
        result = engine.reconcile(
            sample_processor_transactions,
            sample_processor_transactions,
            date(2025, 9, 30),
            "stripe",
        )
        assert result.summary.missing_transactions_count == 0
        assert result.summary.total_discrepancy_amount == Decimal("0.00")
        assert len(result.missing_transactions_details) == 0

    def test_reconcile_all_missing(self, engine, sample_processor_transactions):
        """All transactions are missing from internal dataset."""
        result = engine.reconcile(
            sample_processor_transactions,
            [],
            date(2025, 9, 30),
            "stripe",
        )
        assert result.summary.missing_transactions_count == 3
        assert result.summary.processor_transactions == 3
        assert result.summary.internal_transactions == 0
        assert len(result.missing_transactions_details) == 3

    def test_reconcile_empty_datasets(self, engine):
        """Reconciliation handles empty processor and internal datasets."""
        result = engine.reconcile([], [], date(2025, 9, 30), "stripe")
        assert result.summary.missing_transactions_count == 0
        assert result.summary.processor_transactions == 0
        assert result.summary.internal_transactions == 0
        assert result.summary.total_discrepancy_amount == Decimal("0.00")

    # ---------------------------
    # Edge Cases & Data Integrity
    # ---------------------------
    def test_reconcile_handles_duplicate_ids_in_processor(self, engine):
        """Duplicate transaction IDs in processor data are handled (first occurrence kept)."""
        duplicate_transactions = [
            Transaction(
                transaction_id="TXN_DUP",
                processor_name="stripe",
                amount=Decimal("100.00"),
                currency="USD",
                status="completed",
                merchant_id="MERCH_001",
                transaction_date=datetime(2025, 9, 30, 10, 0, 0),
                reference_number="REF_001",
                fee=Decimal("3.20"),
            ),
            Transaction(
                transaction_id="TXN_DUP",
                processor_name="stripe",
                amount=Decimal("200.00"),
                currency="USD",
                status="completed",
                merchant_id="MERCH_002",
                transaction_date=datetime(2025, 9, 30, 11, 0, 0),
                reference_number="REF_002",
                fee=Decimal("6.20"),
            ),
        ]
        result = engine.reconcile(duplicate_transactions, [], date(2025, 9, 30), "stripe")
        assert result.summary.processor_transactions == 1
        assert result.summary.missing_transactions_count == 1

    def test_reconcile_result_structure(
        self, engine, sample_processor_transactions, sample_internal_transactions
    ):
        """Check ReconciliationResult structure and summary correctness."""
        result = engine.reconcile(
            sample_processor_transactions,
            sample_internal_transactions,
            date(2025, 9, 30),
            "stripe",
        )
        assert isinstance(result, ReconciliationResult)
        assert result.processor == "stripe"
        assert result.reconciliation_date == date(2025, 9, 30)
        assert hasattr(result, "summary")
        assert hasattr(result, "missing_transactions_details")
        assert result.summary.processor_transactions == 3
        assert result.summary.internal_transactions == 2

    def test_reconcile_preserves_transaction_details(
        self, engine, sample_processor_transactions
    ):
        """Missing transaction details are fully preserved in result."""
        result = engine.reconcile(sample_processor_transactions, [], date(2025, 9, 30), "stripe")
        for txn in result.missing_transactions_details:
            assert txn.transaction_id is not None
            assert txn.amount > 0
            assert txn.currency == "USD"
            assert txn.merchant_id is not None
            assert txn.fee is not None

    # ---------------------------
    # Performance & Scaling
    # ---------------------------
    def test_reconcile_large_dataset_performance(self, engine):
        """Reconcile 1000 transactions with 10 missing efficiently (<1s)."""
        processor_set = [
            Transaction(
                transaction_id=f"TXN_{i:04d}",
                processor_name="stripe",
                amount=Decimal("100.00"),
                currency="USD",
                status="completed",
                merchant_id=f"MERCH_{i}",
                transaction_date=datetime(2025, 9, 30, 10, 0, 0),
                reference_number=f"REF_{i}",
                fee=Decimal("3.20"),
            ) for i in range(1000)
        ]
        internal_set = processor_set[:990]  # 10 missing

        start = time.time()
        result = engine.reconcile(processor_set, internal_set, date(2025, 9, 30), "stripe")
        elapsed = time.time() - start

        assert result.summary.missing_transactions_count == 10
        assert elapsed < 1.0

    # ---------------------------
    # Internal Helper Methods
    # ---------------------------
    def test_build_index_creates_correct_mapping(self, engine, sample_processor_transactions):
        """_build_index returns correct mapping of transaction_id to Transaction."""
        index = engine._build_index(sample_processor_transactions)
        assert len(index) == 3
        assert "TXN_STRIPE_20250930_0001" in index
        assert index["TXN_STRIPE_20250930_0001"].amount == Decimal("100.00")

    def test_reconcile_with_different_processors(self, engine):
        """Reconciliation works with various processor names."""
        for processor in ["stripe", "paypal", "square"]:
            txn = Transaction(
                transaction_id=f"TXN_{processor.upper()}_0001",
                processor_name=processor,
                amount=Decimal("100.00"),
                currency="USD",
                status="completed",
                merchant_id="MERCH_001",
                transaction_date=datetime(2025, 9, 30, 10, 0, 0),
                reference_number="REF_001",
                fee=Decimal("3.20"),
            )
            result = engine.reconcile([txn], [], date(2025, 9, 30), processor)
            assert result.processor == processor
            assert result.summary.processor == processor
