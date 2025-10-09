"""
report_generator.py

## Reconciliation Reporting Module

This module defines the ReportGenerator class, responsible for transforming the
results of the reconciliation process into various required output formats:
Detailed CSV, structured JSON (for APIs), and a human-readable Executive Summary.
It utilizes **Pandas** for efficient data manipulation.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd
import structlog

from models import ReconciliationResult, Transaction

logger = structlog.get_logger()


class ReportGenerator:
    """Builds CSV, JSON, and Executive Text summaries from reconciliation data."""

    def __init__(self, report_prefix: str = "reconciliation_report") -> None:
        """Initialize with a standard report filename prefix."""
        self.report_prefix = report_prefix

    def generate_all_reports(
        self, result: ReconciliationResult, output_dir: Path
    ) -> Tuple[Path, str, Path]:
        """
        Generates all required report formats (CSV, JSON, Summary Text) and writes them to disk.

        Creates the output directory if it doesn't exist.

        Returns: (CSV Path, Executive Summary Text, JSON Path)
        """
        # Validate and normalize output directory path
        normalized_path = output_dir.resolve()
        cwd = Path.cwd()
        allowed_dirs = [cwd, cwd / "reports", cwd / "local_reports"]
        
        is_allowed = any(
            normalized_path.is_relative_to(allowed_dir) 
            for allowed_dir in allowed_dirs if allowed_dir.exists()
        )
        is_temp = "tmp" in str(normalized_path).lower()
        
        if not (is_allowed or is_temp):
            raise ValueError("Invalid output directory path detected")
        normalized_path.mkdir(parents=True, exist_ok=True)

        # 1. Generate Detailed CSV
        csv_path = self._generate_detailed_csv(result, output_dir)

        # 2. Generate Executive Summary (Text)
        summary_text = self._generate_executive_summary(result)

        # 3. Generate JSON Report (API Contract)
        json_path = self._generate_json_report(result, output_dir)

        return csv_path, summary_text, json_path

    # -------------------------------------------------------------------------
    # Private Report Generation Methods
    # -------------------------------------------------------------------------

    def _generate_detailed_csv(
        self, result: ReconciliationResult, output_dir: Path
    ) -> Path:
        """Generates a detailed CSV file of all missing transactions using Pandas."""

        filename = f"{self.report_prefix}_{result.processor}_{result.reconciliation_date.isoformat()}.csv"
        csv_path = output_dir / filename

        # Convert transaction objects to DataFrame-compatible format
        data = [
            t.model_dump() if hasattr(t, "model_dump") else t.__dict__
            for t in result.missing_transactions_details
        ]

        if not data:
            # Create empty DataFrame with Transaction model columns
            df = pd.DataFrame(columns=list(Transaction.__annotations__.keys()))
        else:
            df = pd.DataFrame(data)

        # Write CSV
        df.to_csv(csv_path, index=False)
        logger.info("Wrote detailed CSV report", path=str(csv_path))
        return csv_path

    def _generate_executive_summary(self, result: ReconciliationResult) -> str:
        """Constructs a human-readable summary text report, including risk analysis."""

        summary = result.summary
        financial_impact = self._calculate_financial_impact(result)

        report = f"""
FinTech Reconciliation Executive Summary
========================================

Date: {result.reconciliation_date}
Processor: {result.processor}
Report Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

RECONCILIATION OVERVIEW
-----------------------
✓ Processor Transactions Processed: {summary.processor_transactions:,}
✓ Internal System Matches: {summary.internal_transactions:,}
⚠ Discrepancies Identified: {summary.missing_transactions_count:,}

FINANCIAL IMPACT
----------------
• Total Transaction Volume: ${financial_impact['total_volume']:,.2f}
• Missing Transaction Value: ${summary.total_discrepancy_amount:,.2f}
• Discrepancy Rate: {financial_impact['discrepancy_rate']:.2%}
• Estimated Processing Fees at Risk: ${financial_impact['fees_at_risk']:,.2f}

RISK ASSESSMENT
---------------
Risk Level: {financial_impact['risk_level']}
Compliance Status: {financial_impact['compliance_status']}

RECOMMENDED ACTIONS
-------------------
{self._generate_recommendations(result)}

"""
        return report.strip()

    def _generate_json_report(
        self, result: ReconciliationResult, output_dir: Path
    ) -> Path:
        """Generates a structured JSON report for downstream systems or APIs."""

        filename = f"{self.report_prefix}_{result.processor}_{result.reconciliation_date.isoformat()}.json"
        json_path = output_dir / filename

        # Serialize Pydantic result object into a standard dictionary structure
        report_data = {
            "report_metadata": {"generated_at": datetime.utcnow().isoformat()},
            "reconciliation_summary": {
                "date": str(result.reconciliation_date),
                "processor": result.processor,
                "processor_transactions": result.summary.processor_transactions,
                # Preserve Decimal precision using string conversion
                "total_discrepancy_amount": str(result.summary.total_discrepancy_amount),
                "total_volume_processed": str(result.summary.total_volume_processed),
            },
            "missing_transactions": [
                t.model_dump() if hasattr(t, "model_dump") else t.__dict__
                for t in result.missing_transactions_details
            ],
            "financial_impact": self._calculate_financial_impact(result),
        }

        # Write JSON with proper serialization handling
        with open(json_path, "w") as f:
            json.dump(report_data, f, indent=2, default=str)

        logger.info("Wrote JSON report", path=str(json_path))
        return json_path

    def _calculate_financial_impact(
        self, result: ReconciliationResult
    ) -> Dict[str, Any]:
        """Calculates financial and risk metrics for inclusion in reports."""
        summary = result.summary

        total_volume = summary.total_volume_processed

        discrepancy_rate = (
            summary.missing_transactions_count / summary.processor_transactions
            if summary.processor_transactions > 0
            else 0
        )

        # Sum of fees on the missing transactions
        fees_at_risk = sum(t.fee for t in result.missing_transactions_details)

        # Simple risk assessment logic based on discrepancy rate
        if discrepancy_rate < 0.001:
            risk_level = "LOW"
        elif discrepancy_rate < 0.005:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        return {
            "total_volume": float(total_volume),
            "discrepancy_rate": discrepancy_rate,
            "fees_at_risk": float(fees_at_risk),
            "risk_level": risk_level,
            "compliance_status": "COMPLIANT" if risk_level == "LOW" else "NEEDS_REVIEW",
            "delay_risk": "HIGH" if summary.missing_transactions_count > 10 else "LOW",
        }

    def _generate_recommendations(self, result: ReconciliationResult) -> str:
        """
        Generates actionable recommendations based on reconciliation results.
        
        Args:
            result: ReconciliationResult containing summary and transaction details
            
        Returns:
            Formatted string with newline-separated recommendations
        """

        recommendations = []

        if result.summary.missing_transactions_count > 0:
            recommendations.append(
                "• Review and reprocess missing transactions within 24 hours"
            )
        else:
            recommendations.append(
                "✓ No action required - all transactions reconciled successfully"
            )

        if float(result.summary.total_discrepancy_amount) > 10000:
            recommendations.append(
                "• PRIORITY: Contact payment processor for missing high-value transactions"
            )

        return "\n".join(recommendations)
