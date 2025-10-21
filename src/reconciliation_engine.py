"""
Core reconciliation logic for comparing transaction datasets.

Compares processor and internal transaction records to identify discrepancies.
Uses hash map indexing for O(1) lookup performance and Decimal for precision.
"""

from __future__ import annotations
import logging
from datetime import date
from decimal import Decimal
from typing import Dict, List

from models import ReconciliationResult, ReconciliationSummary, Transaction

# Standard logger for audit trail and operational monitoring
logger = logging.getLogger(__name__)


class ReconciliationEngine:
    """Compares transaction datasets and identifies missing records."""

    def __init__(self) -> None:
        """Initialize reconciliation engine."""
        pass

    @staticmethod
    def _build_index(transactions: List[Transaction]) -> Dict[str, Transaction]:
        """Build transaction index for O(1) lookups."""
        index: Dict[str, Transaction] = {}
        for t in transactions:
            if t.transaction_id in index:
                logger.warning(
                    "Duplicate transaction_id %s encountered; keeping first occurrence.",
                    t.transaction_id,
                )
                continue
            index[t.transaction_id] = t
        return index

    def reconcile(
        self,
        processor_transactions: List[Transaction],
        internal_transactions: List[Transaction],
        run_date: date,
        processor: str,
    ) -> ReconciliationResult:
        """
        Execute reconciliation between processor and internal transactions.
        
        Args:
            processor_transactions: Transactions from payment processor
            internal_transactions: Transactions from internal systems
            run_date: Date of reconciliation run
            processor: Name of payment processor
            
        Returns:
            ReconciliationResult with summary and missing transaction details
        """


        proc_index = self._build_index(processor_transactions)
        int_index = self._build_index(internal_transactions)
        unique_proc_txns = list(proc_index.values())

        missing_details: List[Transaction] = []


        for tid, p_txn in proc_index.items():
            if tid not in int_index:
                missing_details.append(p_txn)
                logger.debug("Missing transaction found: %s", tid)


        total_discrepancy: Decimal = sum(t.amount for t in missing_details)
        total_volume: Decimal = sum(t.amount for t in unique_proc_txns)


        summary = ReconciliationSummary(
            reconciliation_date=run_date,
            processor=processor,
            processor_transactions=len(unique_proc_txns),
            internal_transactions=len(int_index),
            missing_transactions_count=len(missing_details),
            total_discrepancy_amount=total_discrepancy,
            total_volume_processed=total_volume,
        )


        result = ReconciliationResult(
            reconciliation_date=run_date,
            processor=processor,
            summary=summary,
            missing_transactions_details=[t.model_dump() for t in missing_details],
        )

        logger.info(
            "Reconciliation complete: %d missing of %d processor transactions "
            "(Total Volume: %s, Discrepancy: %s)",
            len(missing_details),
            len(unique_proc_txns),
            total_volume,
            total_discrepancy,
        )

        return result
