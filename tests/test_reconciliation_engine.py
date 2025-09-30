"""
Unit tests for ReconciliationEngine
Tests core business logic: transaction comparison, discrepancy detection, financial calculations
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import pytest
from datetime import date, datetime
from decimal import Decimal
from reconciliation_engine import ReconciliationEngine
from models import Transaction, ReconciliationResult


class TestReconciliationEngine:
    """Test suite for ReconciliationEngine class"""

    @pytest.fixture
    def engine(self):
        """Create a ReconciliationEngine instance for testing"""
        return ReconciliationEngine()

    @pytest.fixture
    def sample_processor_transactions(self):
        """Create sample processor transactions"""
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
                fee=Decimal("3.20")
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
                fee=Decimal("7.56")
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
                fee=Decimal("1.75")
            ),
        ]

    @pytest.fixture
    def sample_internal_transactions(self):
        """Create sample internal transactions (missing TXN_0002)"""
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
                fee=Decimal("3.20")
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
                fee=Decimal("1.75")
            ),
        ]

    def test_reconcile_identifies_missing_transactions(self, engine, sample_processor_transactions, sample_internal_transactions):
        """Test that reconciliation correctly identifies missing transactions"""
        result = engine.reconcile(
            sample_processor_transactions,
            sample_internal_transactions,
            date(2025, 9, 30),
            "stripe"
        )

        assert result.summary.missing_transactions_count == 1
        assert len(result.missing_transactions_details) == 1
        assert result.missing_transactions_details[0].transaction_id == "TXN_STRIPE_20250930_0002"

    def test_reconcile_calculates_discrepancy_amount(self, engine, sample_processor_transactions, sample_internal_transactions):
        """Test that total discrepancy amount is calculated correctly"""
        result = engine.reconcile(
            sample_processor_transactions,
            sample_internal_transactions,
            date(2025, 9, 30),
            "stripe"
        )

        expected_discrepancy = Decimal("250.50")  # Amount of missing transaction
        assert result.summary.total_discrepancy_amount == expected_discrepancy

    def test_reconcile_calculates_total_volume(self, engine, sample_processor_transactions, sample_internal_transactions):
        """Test that total volume processed is calculated correctly"""
        result = engine.reconcile(
            sample_processor_transactions,
            sample_internal_transactions,
            date(2025, 9, 30),
            "stripe"
        )

        expected_volume = Decimal("100.00") + Decimal("250.50") + Decimal("50.00")
        assert result.summary.total_volume_processed == expected_volume

    def test_reconcile_perfect_match(self, engine, sample_processor_transactions):
        """Test reconciliation when all transactions match"""
        result = engine.reconcile(
            sample_processor_transactions,
            sample_processor_transactions,  # Same data = perfect match
            date(2025, 9, 30),
            "stripe"
        )

        assert result.summary.missing_transactions_count == 0
        assert result.summary.total_discrepancy_amount == Decimal("0.00")
        assert len(result.missing_transactions_details) == 0

    def test_reconcile_all_missing(self, engine, sample_processor_transactions):
        """Test reconciliation when all processor transactions are missing from internal"""
        result = engine.reconcile(
            sample_processor_transactions,
            [],  # Empty internal list
            date(2025, 9, 30),
            "stripe"
        )

        assert result.summary.missing_transactions_count == 3
        assert result.summary.processor_transactions == 3
        assert result.summary.internal_transactions == 0
        assert len(result.missing_transactions_details) == 3

    def test_reconcile_empty_datasets(self, engine):
        """Test reconciliation with empty datasets"""
        result = engine.reconcile(
            [],
            [],
            date(2025, 9, 30),
            "stripe"
        )

        assert result.summary.missing_transactions_count == 0
        assert result.summary.processor_transactions == 0
        assert result.summary.internal_transactions == 0
        assert result.summary.total_discrepancy_amount == Decimal("0.00")

    def test_reconcile_handles_duplicate_ids_in_processor(self, engine):
        """Test that duplicate transaction IDs are handled (first occurrence kept)"""
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
                fee=Decimal("3.20")
            ),
            Transaction(
                transaction_id="TXN_DUP",  # Duplicate ID
                processor_name="stripe",
                amount=Decimal("200.00"),  # Different amount
                currency="USD",
                status="completed",
                merchant_id="MERCH_002",
                transaction_date=datetime(2025, 9, 30, 11, 0, 0),
                reference_number="REF_002",
                fee=Decimal("6.20")
            ),
        ]

        result = engine.reconcile(
            duplicate_transactions,
            [],
            date(2025, 9, 30),
            "stripe"
        )

        # Should only count 1 transaction (first occurrence)
        assert result.summary.processor_transactions == 1
        assert result.summary.missing_transactions_count == 1

    def test_reconcile_result_structure(self, engine, sample_processor_transactions, sample_internal_transactions):
        """Test that ReconciliationResult has correct structure"""
        result = engine.reconcile(
            sample_processor_transactions,
            sample_internal_transactions,
            date(2025, 9, 30),
            "stripe"
        )

        # Check result structure
        assert isinstance(result, ReconciliationResult)
        assert result.processor == "stripe"
        assert result.reconciliation_date == date(2025, 9, 30)
        assert hasattr(result, 'summary')
        assert hasattr(result, 'missing_transactions_details')

        # Check summary structure
        assert result.summary.processor_transactions == 3
        assert result.summary.internal_transactions == 2

    def test_reconcile_preserves_transaction_details(self, engine, sample_processor_transactions):
        """Test that missing transaction details are preserved correctly"""
        result = engine.reconcile(
            sample_processor_transactions,
            [],
            date(2025, 9, 30),
            "stripe"
        )

        # Check all missing transactions have complete details
        for missing_txn in result.missing_transactions_details:
            assert missing_txn.transaction_id is not None
            assert missing_txn.amount > 0
            assert missing_txn.currency == "USD"
            assert missing_txn.merchant_id is not None
            assert missing_txn.fee is not None

    def test_reconcile_large_dataset_performance(self, engine):
        """Test reconciliation performance with larger dataset"""
        # Create 1000 processor transactions
        large_processor_set = [
            Transaction(
                transaction_id=f"TXN_{i:04d}",
                processor_name="stripe",
                amount=Decimal("100.00"),
                currency="USD",
                status="completed",
                merchant_id=f"MERCH_{i}",
                transaction_date=datetime(2025, 9, 30, 10, 0, 0),
                reference_number=f"REF_{i}",
                fee=Decimal("3.20")
            )
            for i in range(1000)
        ]

        # Create 990 internal transactions (10 missing)
        large_internal_set = [
            Transaction(
                transaction_id=f"TXN_{i:04d}",
                processor_name="stripe",
                amount=Decimal("100.00"),
                currency="USD",
                status="completed",
                merchant_id=f"MERCH_{i}",
                transaction_date=datetime(2025, 9, 30, 10, 0, 0),
                reference_number=f"REF_{i}",
                fee=Decimal("3.20")
            )
            for i in range(990)
        ]

        import time
        start_time = time.time()
        result = engine.reconcile(
            large_processor_set,
            large_internal_set,
            date(2025, 9, 30),
            "stripe"
        )
        elapsed_time = time.time() - start_time

        assert result.summary.missing_transactions_count == 10
        assert elapsed_time < 1.0  # Should complete in less than 1 second

    def test_build_index_creates_correct_mapping(self, engine, sample_processor_transactions):
        """Test internal _build_index method"""
        index = engine._build_index(sample_processor_transactions)

        assert len(index) == 3
        assert "TXN_STRIPE_20250930_0001" in index
        assert index["TXN_STRIPE_20250930_0001"].amount == Decimal("100.00")

    def test_reconcile_with_different_processors(self, engine):
        """Test reconciliation works with different processor names"""
        for processor in ["stripe", "paypal", "square"]:
            transactions = [
                Transaction(
                    transaction_id=f"TXN_{processor.upper()}_0001",
                    processor_name=processor,
                    amount=Decimal("100.00"),
                    currency="USD",
                    status="completed",
                    merchant_id="MERCH_001",
                    transaction_date=datetime(2025, 9, 30, 10, 0, 0),
                    reference_number="REF_001",
                    fee=Decimal("3.20")
                )
            ]

            result = engine.reconcile(transactions, [], date(2025, 9, 30), processor)
            assert result.processor == processor
            assert result.summary.processor == processor