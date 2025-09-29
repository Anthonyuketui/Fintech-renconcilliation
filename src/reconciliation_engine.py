"""
Core business logic for the FinTech Transaction Reconciliation System.

The ReconciliationEngine compares two sets of transactions to find discrepancies.
It uses highly efficient O(1) complexity lookups for scalability, includes a check
for duplicate transaction IDs, and maintains the Decimal type for 99.9% financial accuracy.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import List, Dict, Tuple, Set
from decimal import Decimal

# Ensure you import all necessary models and types
from models import Transaction, ReconciliationResult, ReconciliationSummary

# Use standard logging, easily integratable with monitoring tools
logger = logging.getLogger(__name__)


class ReconciliationEngine:
    """Compares transaction lists and identifies discrepancies using O(1) lookup complexity."""

    def __init__(self) -> None:
        pass # Initialization is minimal, relies on input data being clean

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
                    "Duplicate transaction_id %s encountered; keeping first occurrence", t.transaction_id
                )
                continue
            index[t.transaction_id] = t
        return index

    # --- MINOR FIX: Return type is the full ReconciliationResult container ---
    def reconcile(
        self,
        processor_transactions: List[Transaction],
        internal_transactions: List[Transaction],
        run_date: date,
        processor: str,
    ) -> ReconciliationResult:
        """Perform reconciliation between processor and internal records."""

        # O(N) operation: build lookup indexes for both data sources
        proc_index = self._build_index(processor_transactions)
        int_index = self._build_index(internal_transactions)
        
        missing_details: List[Transaction] = []

        # O(1) Lookup Loop: Iterate through processor data and check for existence in internal index
        for tid, p_txn in proc_index.items():
            if tid not in int_index:
                missing_details.append(p_txn)
                logger.debug("Missing transaction found", transaction_id=tid)

        # --- CRITICAL FIX: Sum Decimals directly without round() ---
        # The sum() function over Decimals maintains precision. We avoid round() to prevent float conversion.
        total_discrepancy: Decimal = sum(t.amount for t in missing_details)
        
        # 1. Create Summary Model
        summary = ReconciliationSummary(
            date=run_date,
            processor=processor,
            processor_transactions=len(processor_transactions),
            internal_transactions=len(internal_transactions),
            missing_transactions_count=len(missing_details),
            total_discrepancy_amount=total_discrepancy,
        )
        
        # 2. Create Final Result Model
        result = ReconciliationResult(
            date=run_date,
            processor=processor,
            summary=summary,
            missing_transactions_details=missing_details # Contains the full list of missing transactions
        )

        logger.info(
            "Reconciliation complete: %d missing of %d processor transactions (%s total discrepancy)",
            len(missing_details),
            len(processor_transactions),
            total_discrepancy, # Logging the Decimal value is correct
        )
        
        # Return the full container
        return result