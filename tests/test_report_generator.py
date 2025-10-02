"""
Unit tests for ReportGenerator
Tests CSV generation, JSON reports, executive summaries, and financial calculations
"""

import sys
import csv
import json
import shutil
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from models import ReconciliationResult, ReconciliationSummary, Transaction
from report_generator import ReportGenerator


class TestReportGenerator:
    """Test suite for ReportGenerator class"""

    @pytest.fixture
    def generator(self):
        """Create a ReportGenerator instance for testing"""
        return ReportGenerator()

    @pytest.fixture
    def temp_output_dir(self):
        """Create a temporary directory for test outputs"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        # Cleanup after test
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    @pytest.fixture
    def sample_reconciliation_result(self):
        """Create a sample reconciliation result with missing transactions"""
        missing_transactions = [
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
        ]

        summary = ReconciliationSummary(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            processor_transactions=30,
            internal_transactions=28,
            missing_transactions_count=2,
            total_discrepancy_amount=Decimal("350.50"),
            total_volume_processed=Decimal("5000.00"),
        )

        return ReconciliationResult(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            summary=summary,
            missing_transactions_details=missing_transactions,
        )

    @pytest.fixture
    def perfect_reconciliation_result(self):
        """Create a result with no discrepancies"""
        summary = ReconciliationSummary(
            processor="paypal",
            reconciliation_date=date(2025, 9, 30),
            processor_transactions=50,
            internal_transactions=50,
            missing_transactions_count=0,
            total_discrepancy_amount=Decimal("0.00"),
            total_volume_processed=Decimal("10000.00"),
        )

        return ReconciliationResult(
            processor="paypal",
            reconciliation_date=date(2025, 9, 30),
            summary=summary,
            missing_transactions_details=[],
        )

    def test_generator_initialization(self, generator):
        """Test ReportGenerator initializes correctly"""
        assert generator.report_prefix == "reconciliation_report"

    def test_generator_custom_prefix(self):
        """Test custom report prefix"""
        generator = ReportGenerator(report_prefix="custom_report")
        assert generator.report_prefix == "custom_report"

    def test_generate_all_reports(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test that all reports are generated"""
        csv_path, summary_text, json_path = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        # Check all files are created
        assert csv_path.exists()
        assert json_path.exists()
        assert isinstance(summary_text, str)
        assert len(summary_text) > 0

    def test_csv_report_structure(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test CSV report has correct structure and data"""
        csv_path, _, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        # Read and validate CSV
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2  # Two missing transactions
        assert "transaction_id" in rows[0]
        assert "amount" in rows[0]
        assert "processor_name" in rows[0]

    def test_csv_report_filename(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test CSV filename follows naming convention"""
        csv_path, _, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        expected_name = "reconciliation_report_stripe_2025-09-30.csv"
        assert csv_path.name == expected_name

    def test_csv_report_empty_discrepancies(
        self, generator, temp_output_dir, perfect_reconciliation_result
    ):
        """Test CSV generation with no missing transactions"""
        csv_path, _, _ = generator.generate_all_reports(
            perfect_reconciliation_result, temp_output_dir
        )

        # CSV should still be created with headers
        assert csv_path.exists()

        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 0  # No data rows, but headers present

    def test_json_report_structure(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test JSON report has correct structure"""
        _, _, json_path = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        with open(json_path, "r") as f:
            data = json.load(f)

        # Validate structure
        assert "report_metadata" in data
        assert "reconciliation_summary" in data
        assert "missing_transactions" in data
        assert "financial_impact" in data

    def test_json_report_metadata(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test JSON report metadata"""
        _, _, json_path = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        with open(json_path, "r") as f:
            data = json.load(f)

        assert "generated_at" in data["report_metadata"]
        # Validate it's a valid ISO timestamp
        datetime.fromisoformat(data["report_metadata"]["generated_at"])

    def test_json_report_summary_data(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test JSON summary contains correct data"""
        _, _, json_path = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        with open(json_path, "r") as f:
            data = json.load(f)

        summary = data["reconciliation_summary"]
        assert summary["date"] == "2025-09-30"
        assert summary["processor"] == "stripe"
        assert summary["processor_transactions"] == 30
        assert float(summary["total_discrepancy_amount"]) == 350.50

    def test_json_report_filename(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test JSON filename follows naming convention"""
        _, _, json_path = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        expected_name = "reconciliation_report_stripe_2025-09-30.json"
        assert json_path.name == expected_name

    def test_executive_summary_content(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test executive summary contains all required sections"""
        _, summary_text, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        # Check for key sections
        assert "Executive Summary" in summary_text
        assert "RECONCILIATION OVERVIEW" in summary_text
        assert "FINANCIAL IMPACT" in summary_text
        assert "RISK ASSESSMENT" in summary_text
        assert "RECOMMENDED ACTIONS" in summary_text

    def test_executive_summary_metrics(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test executive summary contains correct metrics"""
        _, summary_text, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        assert "stripe" in summary_text.lower()
        assert "2025-09-30" in summary_text
        assert "30" in summary_text  # processor transactions
        assert "28" in summary_text  # internal transactions
        assert "2" in summary_text  # missing transactions

    def test_calculate_financial_impact(self, generator, sample_reconciliation_result):
        """Test financial impact calculation"""
        impact = generator._calculate_financial_impact(sample_reconciliation_result)

        assert "total_volume" in impact
        assert "discrepancy_rate" in impact
        assert "fees_at_risk" in impact
        assert "risk_level" in impact
        assert "compliance_status" in impact

    def test_calculate_financial_impact_values(
        self, generator, sample_reconciliation_result
    ):
        """Test financial impact calculation produces correct values"""
        impact = generator._calculate_financial_impact(sample_reconciliation_result)

        assert impact["total_volume"] == 5000.00
        # discrepancy_rate = 2 / 30 = 0.0667
        assert abs(impact["discrepancy_rate"] - 0.0667) < 0.001
        # fees_at_risk = sum of fees in missing transactions
        expected_fees = 3.20 + 7.56
        assert abs(impact["fees_at_risk"] - expected_fees) < 0.01

    def test_risk_level_low(self, generator):
        """Test risk level assessment for low discrepancy"""
        summary = ReconciliationSummary(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            processor_transactions=10000,
            internal_transactions=9999,
            missing_transactions_count=1,  # 0.01% discrepancy
            total_discrepancy_amount=Decimal("10.00"),
            total_volume_processed=Decimal("100000.00"),
        )
        result = ReconciliationResult(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            summary=summary,
            missing_transactions_details=[],
        )

        impact = generator._calculate_financial_impact(result)
        assert impact["risk_level"] == "LOW"

    def test_risk_level_medium(self, generator):
        """Test risk level assessment for medium discrepancy"""
        summary = ReconciliationSummary(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            processor_transactions=1000,
            internal_transactions=997,
            missing_transactions_count=3,  # 0.3% discrepancy
            total_discrepancy_amount=Decimal("300.00"),
            total_volume_processed=Decimal("10000.00"),
        )
        result = ReconciliationResult(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            summary=summary,
            missing_transactions_details=[],
        )

        impact = generator._calculate_financial_impact(result)
        assert impact["risk_level"] == "MEDIUM"

    def test_risk_level_high(self, generator):
        """Test risk level assessment for high discrepancy"""
        summary = ReconciliationSummary(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            processor_transactions=100,
            internal_transactions=94,
            missing_transactions_count=6,  # 6% discrepancy
            total_discrepancy_amount=Decimal("6000.00"),
            total_volume_processed=Decimal("10000.00"),
        )
        result = ReconciliationResult(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            summary=summary,
            missing_transactions_details=[],
        )

        impact = generator._calculate_financial_impact(result)
        assert impact["risk_level"] == "HIGH"

    def test_compliance_status_compliant(
        self, generator, perfect_reconciliation_result
    ):
        """Test compliance status when risk is low"""
        impact = generator._calculate_financial_impact(perfect_reconciliation_result)
        assert impact["compliance_status"] == "COMPLIANT"

    def test_generate_recommendations_with_discrepancies(
        self, generator, sample_reconciliation_result
    ):
        """Test recommendations when discrepancies exist"""
        recommendations = generator._generate_recommendations(
            sample_reconciliation_result
        )

        assert "Review and reprocess" in recommendations
        assert "24 hours" in recommendations

    def test_generate_recommendations_no_discrepancies(
        self, generator, perfect_reconciliation_result
    ):
        """Test recommendations when no discrepancies"""
        recommendations = generator._generate_recommendations(
            perfect_reconciliation_result
        )

        assert "No action required" in recommendations
        assert "successfully" in recommendations.lower()

    def test_generate_recommendations_high_value(self, generator):
        """Test recommendations for high-value discrepancies"""
        summary = ReconciliationSummary(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            processor_transactions=100,
            internal_transactions=99,
            missing_transactions_count=1,
            total_discrepancy_amount=Decimal("15000.00"),  # High value
            total_volume_processed=Decimal("100000.00"),
        )
        result = ReconciliationResult(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            summary=summary,
            missing_transactions_details=[],
        )

        recommendations = generator._generate_recommendations(result)
        assert "PRIORITY" in recommendations
        assert "payment processor" in recommendations.lower()

    def test_output_directory_creation(self, generator, sample_reconciliation_result):
        """Test that output directory is created if it doesn't exist"""
        temp_dir = Path(tempfile.mkdtemp())
        output_dir = temp_dir / "nested" / "reports"

        # Directory doesn't exist yet
        assert not output_dir.exists()

        generator.generate_all_reports(sample_reconciliation_result, output_dir)

        # Should be created
        assert output_dir.exists()

        # Cleanup
        shutil.rmtree(temp_dir)

    def test_decimal_serialization_in_json(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test that Decimal values are properly serialized in JSON"""
        _, _, json_path = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        with open(json_path, "r") as f:
            data = json.load(f)

        # All numeric values should be properly serialized (no Decimal objects in JSON)
        assert isinstance(
            data["reconciliation_summary"]["total_discrepancy_amount"], (int, float)
        )
        assert isinstance(data["financial_impact"]["total_volume"], (int, float))

    def test_csv_preserves_decimal_precision(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test that CSV preserves decimal precision for amounts"""
        csv_path, _, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Check first transaction amount
        assert rows[0]["amount"] == "100.00"
        assert rows[0]["fee"] == "3.20"

    def test_generate_reports_with_different_processors(
        self, generator, temp_output_dir
    ):
        """Test report generation for different processors"""
        for processor in ["stripe", "paypal", "square"]:
            summary = ReconciliationSummary(
                processor=processor,
                reconciliation_date=date(2025, 9, 30),
                processor_transactions=10,
                internal_transactions=10,
                missing_transactions_count=0,
                total_discrepancy_amount=Decimal("0.00"),
                total_volume_processed=Decimal("1000.00"),
            )
            result = ReconciliationResult(
                processor=processor,
                reconciliation_date=date(2025, 9, 30),
                summary=summary,
                missing_transactions_details=[],
            )

            csv_path, summary_text, json_path = generator.generate_all_reports(
                result, temp_output_dir / processor
            )

            assert processor in csv_path.name
            assert processor in json_path.name
            assert processor in summary_text

    def test_executive_summary_formatting(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test executive summary is well-formatted"""
        _, summary_text, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        lines = summary_text.split("\n")

        # Check for proper formatting
        assert any("=" in line for line in lines)  # Has section dividers
        assert any("-" in line for line in lines)  # Has subsection dividers
        assert len(summary_text) > 200  # Substantial content
