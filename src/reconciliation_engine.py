"""
Core business logic for the FinTech Transaction Reconciliation System.

The ReconciliationEngine compares two sets of transactions to find discrepancies.
It uses highly efficient O(1) complexity lookups for scalability, includes a check
for duplicate transaction IDs, and maintains the Decimal type for 99.9% financial accuracy.
"""

from __future__ import annotations
import logging
from datetime import date
from decimal import Decimal
from typing import Dict, List

# Ensure you import all necessary models and types
from models import ReconciliationResult, ReconciliationSummary, Transaction

# Use standard logging, easily integratable with monitoring tools
logger = logging.getLogger(__name__)


class ReconciliationEngine:
    """Compares transaction lists and identifies discrepancies using O(1) lookup complexity."""

    def __init__(self) -> None:
        pass  # Initialization is minimal, relies on input data being clean

    @staticmethod
    def _build_index(transactions: List[Transaction]) -> Dict[str, Transaction]:
        """
        Constructs a mapping from transaction ID to the full transaction object.

        This is an O(N) operation and is necessary for the subsequent O(1) lookups.
        It also includes a critical Data Quality Check for duplicate IDs.
        """
        index: Dict[str, Transaction] = {}
        for t in transactions:
            if t.transaction_id in index:
                # Data Quality Check (V2 Win): Log a warning if a duplicate ID is found.
                logger.warning(
                    "Duplicate transaction_id %s encountered; keeping first occurrence",
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
        """Perform reconciliation between processor and internal records, handling duplicates properly."""

        # --- Deduplicate transactions by transaction_id ---
        proc_index = self._build_index(processor_transactions)
        int_index = self._build_index(internal_transactions)

        # Convert deduplicated processor transactions to a list for calculations
        unique_proc_txns = list(proc_index.values())

        missing_details: List[Transaction] = []

        # Check for missing transactions in internal records
        for tid, p_txn in proc_index.items():
            if tid not in int_index:
                missing_details.append(p_txn)
                logger.debug("Missing transaction found: %s", tid)

        # --- Financial Calculations ---
        total_discrepancy: Decimal = sum(t.amount for t in missing_details)
        total_volume: Decimal = sum(t.amount for t in unique_proc_txns)

        # --- Build Summary ---
        summary = ReconciliationSummary(
            reconciliation_date=run_date,
            processor=processor,
            processor_transactions=len(unique_proc_txns),  # Only unique transactions
            internal_transactions=len(int_index),  # Only unique internal transactions
            missing_transactions_count=len(missing_details),
            total_discrepancy_amount=total_discrepancy,
            total_volume_processed=total_volume,
        )

        # --- Build Result ---
        result = ReconciliationResult(
            reconciliation_date=run_date,
            processor=processor,
            summary=summary,
            # FIX: Use model_dump() for Pydantic V2 nested model validation
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