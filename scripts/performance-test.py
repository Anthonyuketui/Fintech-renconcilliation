#!/usr/bin/env python3
import sys
import os
import time
from datetime import datetime, date
from decimal import Decimal

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from reconciliation_engine import ReconciliationEngine
from models import Transaction

# Generate test data
processor_txns = [Transaction(
    transaction_id=f'txn_{i}',
    processor_name='stripe',
    amount=Decimal('100.0'),
    currency='USD',
    status='completed',
    merchant_id='test_merchant',
    transaction_date=datetime(2025, 1, 1),
    reference_number=f'ref_{i}',
    fee=Decimal('2.9')
) for i in range(10000)]
internal_txns = processor_txns[:-500]  # 500 missing

# Performance test
start_time = time.time()
engine = ReconciliationEngine()
result = engine.reconcile(processor_txns, internal_txns, date(2025, 1, 1), 'stripe')
duration = time.time() - start_time

print(f'Processed 10,000 transactions in {duration:.2f} seconds')
assert duration < 30, f'Performance test failed: {duration:.2f}s > 30s'
assert result.summary.missing_transactions_count == 500, f'Expected 500 missing, got {result.summary.missing_transactions_count}'
print('Performance test passed')