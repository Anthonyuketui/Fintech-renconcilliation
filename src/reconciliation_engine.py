"""
Core business logic for the FinTech Transaction Reconciliation System.

## Reconciliation Engine

This module defines the **ReconciliationEngine**, which compares transactions from two
sources (Processor vs. Internal) to identify missing records and discrepancies.
It uses efficient hash map lookups for **O(1) average complexity** and ensures
**financial precision** by using the Decimal type.
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
    """Compares transaction lists and identifies discrepancies using O(1) lookup complexity."""

    def __init__(self) -> None:
        """Initializes the engine. No internal state is maintained."""
        pass

    @staticmethod
    def _build_index(transactions: List[Transaction]) -> Dict[str, Transaction]:
        """
        Creates an index mapping {transaction_id: Transaction} for fast lookups.

        This index facilitates **O(1) lookups** during reconciliation and automatically
        handles duplicate IDs by logging a warning and keeping the first record.
        """
        index: Dict[str, Transaction] = {}
        for t in transactions:
            if t.transaction_id in index:
                # Log a warning for duplicate transaction IDs encountered in the source data.
                logger.warning(
                    "Duplicate transaction_id %s encountered; only the first is retained.",
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
        Executes the core reconciliation logic and returns a comprehensive result object.
        """

        # --- 1. Indexing and Deduplication ---
        proc_index = self._build_index(processor_transactions)
        int_index = self._build_index(internal_transactions)

        # Get the unique set of processor transactions for comparison and volume calculation
        unique_proc_txns = list(proc_index.values())

        missing_details: List[Transaction] = []

        # --- 2. Identify Missing Transactions (Processor vs. Internal) ---
        # The primary check is identifying transactions present in the processor's data but missing internally.
        for tid, p_txn in proc_index.items():
            if tid not in int_index:
                missing_details.append(p_txn)
                logger.debug("Missing transaction found: %s", tid)

        # --- 3. Financial Totals ---
        total_discrepancy: Decimal = sum(t.amount for t in missing_details)
        total_volume: Decimal = sum(t.amount for t in unique_proc_txns)

        # --- 4. Build Summary Report ---
        summary = ReconciliationSummary(
            reconciliation_date=run_date,
            processor=processor,
            # Report counts based on unique IDs
            processor_transactions=len(unique_proc_txns),
            internal_transactions=len(int_index),
            missing_transactions_count=len(missing_details),
            total_discrepancy_amount=total_discrepancy,
            total_volume_processed=total_volume,
        )

        # --- 5. Build Final Result Object ---
        result = ReconciliationResult(
            reconciliation_date=run_date,
            processor=processor,
            summary=summary,
            # Serialize the missing transaction list for the final Pydantic model
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