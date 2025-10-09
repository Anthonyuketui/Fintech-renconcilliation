"""
Unit tests for ReportGenerator
Covers CSV and JSON report generation, executive summaries, financial impact calculations, and recommendations.
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
    """Test suite for the ReportGenerator class"""

    @pytest.fixture
    def generator(self):
        """Provides a ReportGenerator instance for testing"""
        return ReportGenerator()

    @pytest.fixture
    def temp_output_dir(self):
        """Provides a temporary directory for storing test outputs"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    @pytest.fixture
    def sample_reconciliation_result(self):
        """Provides a sample reconciliation result with missing transactions"""
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
        """Provides a reconciliation result with no discrepancies"""
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

    # ---------------------------
    # Initialization tests
    # ---------------------------
    def test_generator_initialization(self, generator):
        """Verifies that the ReportGenerator initializes with the default prefix"""
        assert generator.report_prefix == "reconciliation_report"

    def test_generator_custom_prefix(self):
        """Verifies that the ReportGenerator accepts a custom report prefix"""
        generator = ReportGenerator(report_prefix="custom_report")
        assert generator.report_prefix == "custom_report"

    # ---------------------------
    # Report generation tests
    # ---------------------------
    def test_generate_all_reports(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Verifies that CSV, JSON, and executive summary are generated correctly"""
        csv_path, summary_text, json_path = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        assert csv_path.exists()
        assert json_path.exists()
        assert isinstance(summary_text, str)
        assert len(summary_text) > 0

    def test_csv_report_structure(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Validates CSV report structure and content"""
        csv_path, _, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert "transaction_id" in rows[0]
        assert "amount" in rows[0]
        assert "processor_name" in rows[0]

    def test_csv_report_filename(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Ensures CSV filename follows the expected naming convention"""
        csv_path, _, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        expected_name = "reconciliation_report_stripe_2025-09-30.csv"
        assert csv_path.name == expected_name

    def test_csv_report_empty_discrepancies(
        self, generator, temp_output_dir, perfect_reconciliation_result
    ):
        """Checks CSV generation when there are no missing transactions"""
        csv_path, _, _ = generator.generate_all_reports(
            perfect_reconciliation_result, temp_output_dir
        )

        assert csv_path.exists()

        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 0

    def test_json_report_structure(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Validates JSON report structure"""
        _, _, json_path = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        with open(json_path, "r") as f:
            data = json.load(f)

        assert "report_metadata" in data
        assert "reconciliation_summary" in data
        assert "missing_transactions" in data
        assert "financial_impact" in data

    def test_json_report_metadata(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Ensures JSON metadata includes generation timestamp in ISO format"""
        _, _, json_path = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        with open(json_path, "r") as f:
            data = json.load(f)

        assert "generated_at" in data["report_metadata"]
        datetime.fromisoformat(data["report_metadata"]["generated_at"])

    def test_json_report_summary_data(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Verifies reconciliation summary data in JSON"""
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
        """Ensures JSON filename follows the expected naming convention"""
        _, _, json_path = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        expected_name = "reconciliation_report_stripe_2025-09-30.json"
        assert json_path.name == expected_name

    # ---------------------------
    # Executive summary tests
    # ---------------------------
    def test_executive_summary_content(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Validates that executive summary includes all required sections"""
        _, summary_text, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        assert "Executive Summary" in summary_text
        assert "RECONCILIATION OVERVIEW" in summary_text
        assert "FINANCIAL IMPACT" in summary_text
        assert "RISK ASSESSMENT" in summary_text
        assert "RECOMMENDED ACTIONS" in summary_text

    def test_executive_summary_metrics(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Checks that executive summary displays correct metrics"""
        _, summary_text, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        assert "stripe" in summary_text.lower()
        assert "2025-09-30" in summary_text
        assert "30" in summary_text
        assert "28" in summary_text
        assert "2" in summary_text

    def test_executive_summary_formatting(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Ensures executive summary is well-formatted with section dividers"""
        _, summary_text, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        lines = summary_text.split("\n")
        assert any("=" in line for line in lines)
        assert any("-" in line for line in lines)
        assert len(summary_text) > 200

    # ---------------------------
    # Financial impact tests
    # ---------------------------
    def test_calculate_financial_impact(self, generator, sample_reconciliation_result):
        """Validates that financial impact calculation produces expected keys"""
        impact = generator._calculate_financial_impact(sample_reconciliation_result)
        assert "total_volume" in impact
        assert "discrepancy_rate" in impact
        assert "fees_at_risk" in impact
        assert "risk_level" in impact
        assert "compliance_status" in impact

    def test_calculate_financial_impact_values(
        self, generator, sample_reconciliation_result
    ):
        """Validates financial impact calculation produces correct values"""
        impact = generator._calculate_financial_impact(sample_reconciliation_result)
        assert impact["total_volume"] == 5000.00
        assert abs(impact["discrepancy_rate"] - 0.0667) < 0.001
        expected_fees = 3.20 + 7.56
        assert abs(impact["fees_at_risk"] - expected_fees) < 0.01

    def test_risk_level_low(self, generator):
        """Ensures risk level is assessed as LOW for minor discrepancies"""
        summary = ReconciliationSummary(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            processor_transactions=10000,
            internal_transactions=9999,
            missing_transactions_count=1,
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
        """Ensures risk level is assessed as MEDIUM for moderate discrepancies"""
        summary = ReconciliationSummary(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            processor_transactions=1000,
            internal_transactions=997,
            missing_transactions_count=3,
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
        """Ensures risk level is assessed as HIGH for major discrepancies"""
        summary = ReconciliationSummary(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            processor_transactions=100,
            internal_transactions=94,
            missing_transactions_count=6,
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
        """Ensures compliance status is COMPLIANT for low-risk results"""
        impact = generator._calculate_financial_impact(perfect_reconciliation_result)
        assert impact["compliance_status"] == "COMPLIANT"

    # ---------------------------
    # Recommendations tests
    # ---------------------------
    def test_generate_recommendations_with_discrepancies(
        self, generator, sample_reconciliation_result
    ):
        """Ensures appropriate recommendations are generated when discrepancies exist"""
        recommendations = generator._generate_recommendations(
            sample_reconciliation_result
        )

        assert "Review and reprocess" in recommendations
        assert "24 hours" in recommendations

    def test_generate_recommendations_no_discrepancies(
        self, generator, perfect_reconciliation_result
    ):
        """Ensures recommendations indicate no action is required when there are no discrepancies"""
        recommendations = generator._generate_recommendations(
            perfect_reconciliation_result
        )

        assert "No action required" in recommendations
        assert "successfully" in recommendations.lower()

    def test_generate_recommendations_high_value(self, generator):
        """Ensures high-value discrepancies are flagged with priority recommendations"""
        summary = ReconciliationSummary(
            processor="stripe",
            reconciliation_date=date(2025, 9, 30),
            processor_transactions=100,
            internal_transactions=99,
            missing_transactions_count=1,
            total_discrepancy_amount=Decimal("15000.00"),
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

    # ---------------------------
    # Miscellaneous tests
    # ---------------------------
    def test_output_directory_creation(self, generator, sample_reconciliation_result):
        """Verifies output directory is created if it does not exist"""
        temp_dir = Path(tempfile.mkdtemp())
        output_dir = temp_dir / "nested" / "reports"

        assert not output_dir.exists()

        generator.generate_all_reports(sample_reconciliation_result, output_dir)
        assert output_dir.exists()

        shutil.rmtree(temp_dir)

    def test_decimal_serialization_in_json(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Ensures Decimal values are properly serialized as numbers in JSON"""
        _, _, json_path = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        with open(json_path, "r") as f:
            data = json.load(f)

        assert isinstance(
            data["reconciliation_summary"]["total_discrepancy_amount"], str
        )
        assert isinstance(data["financial_impact"]["total_volume"], (int, float))

    def test_csv_preserves_decimal_precision(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Ensures CSV output preserves decimal precision for amounts and fees"""
        csv_path, _, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert rows[0]["amount"] == "100.00"
        assert rows[0]["fee"] == "3.20"

    def test_generate_reports_with_different_processors(
        self, generator, temp_output_dir
    ):
        """Verifies report generation works for multiple payment processors"""
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

    def test_executive_summary_format_validation(
        self, generator, temp_output_dir, sample_reconciliation_result
    ):
        """Test executive summary format validation"""
        _, summary_text, _ = generator.generate_all_reports(
            sample_reconciliation_result, temp_output_dir
        )

        lines = summary_text.split("\n")

        # Check for proper formatting
        assert any("=" in line for line in lines)  # Has section dividers
        assert any("-" in line for line in lines)  # Has subsection dividers
        assert len(summary_text) > 200  # Substantial content
