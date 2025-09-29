"""
Production-ready database manager for reconciliation system.
Handles PostgreSQL operations with full transaction safety, UUID support,
data validation, and comprehensive audit logging.
"""

from __future__ import annotations

import os
import json
from contextlib import contextmanager
from typing import Iterable, Optional, Dict, Any, List
from datetime import datetime, date
from decimal import Decimal
import uuid

import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_values, RealDictCursor
from structlog import get_logger

from models import ReconciliationResult, Transaction, Settings

logger = get_logger()


class DatabaseManager:
    """Production-ready PostgreSQL manager with UUID support and comprehensive validation."""

    def __init__(self, settings: Settings = None):
        if settings:
            # Use Settings object for configuration
            self.db_url = settings.DB_URL
        else:
            # Fallback to environment variables
            self.host = os.getenv("DB_HOST", "localhost")
            self.port = int(os.getenv("DB_PORT", "5432"))
            self.dbname = os.getenv("DB_NAME", "fintech_reconciliation")
            self.user = os.getenv("DB_USER", "postgres")
            self.password = os.getenv("DB_PASSWORD")
            self.db_url = f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbname}"

    @contextmanager
    def get_connection(self):
        """Production-ready connection manager with comprehensive error handling."""
        conn = None
        
        if not self.db_url or 'None' in self.db_url:
            logger.warning("Database URL not properly configured; skipping database operations")
            yield None
            return
            
        try:
            conn = psycopg2.connect(self.db_url)
            conn.autocommit = False  # Explicit transaction control
            yield conn
            
        except psycopg2.Error as exc:
            if conn:
                conn.rollback()
            logger.error("Database transaction failed", error=str(exc), error_type=type(exc).__name__)
            raise
            
        except Exception as exc:
            if conn:
                conn.rollback()
            logger.error("Unexpected database error", error=str(exc))
            raise
            
        finally:
            if conn:
                conn.close()

    def store_reconciliation_result(self, result: ReconciliationResult) -> Optional[str]:
        """
        Store complete reconciliation result in a single atomic transaction.
        Returns UUID as string for the reconciliation run.
        """
        
        with self.get_connection() as conn:
            if conn is None:
                return None
                
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Begin explicit transaction
                    cursor.execute("BEGIN")
                    
                    # Generate UUID for this run
                    run_uuid = str(uuid.uuid4())
                    
                    # Insert reconciliation run with full validation
                    cursor.execute("""
                        INSERT INTO reconciliation_runs (
                            id, run_date, processor_name, start_time, end_time, status,
                            processor_transaction_count, internal_transaction_count,
                            missing_transaction_count, total_discrepancy_amount,
                            created_by
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (run_date, processor_name) 
                        DO UPDATE SET 
                            end_time = EXCLUDED.end_time,
                            status = EXCLUDED.status,
                            processor_transaction_count = EXCLUDED.processor_transaction_count,
                            internal_transaction_count = EXCLUDED.internal_transaction_count,
                            missing_transaction_count = EXCLUDED.missing_transaction_count,
                            total_discrepancy_amount = EXCLUDED.total_discrepancy_amount,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id
                    """, (
                        run_uuid,
                        result.date,
                        result.processor,
                        datetime.utcnow(),  # start_time
                        datetime.utcnow(),  # end_time (for completed reconciliation)
                        'completed',
                        result.summary.processor_transactions,
                        result.summary.internal_transactions,
                        result.summary.missing_transactions_count,
                        result.summary.total_discrepancy_amount,
                        'reconciliation_system'
                    ))
                    
                    actual_run_id = cursor.fetchone()['id']
                    
                    # Store missing transactions with bulk insert
                    if result.missing_transactions_details:
                        self._bulk_insert_missing_transactions(
                            cursor, actual_run_id, result.missing_transactions_details
                        )
                    
                    # Perform data quality checks
                    self._perform_data_quality_checks(cursor, actual_run_id, result)
                    
                    # Log comprehensive audit entry
                    self._log_audit_event(
                        cursor,
                        action='reconciliation_completed',
                        table_name='reconciliation_runs',
                        record_id=actual_run_id,
                        new_values={
                            'processor': result.processor,
                            'run_date': result.date.isoformat(),
                            'missing_count': result.summary.missing_transactions_count,
                            'discrepancy_amount': float(result.summary.total_discrepancy_amount),
                            'success_rate': self._calculate_success_rate(result)
                        }
                    )
                    
                    # Commit transaction
                    conn.commit()
                    
                    logger.info(
                        "Successfully stored reconciliation result",
                        run_id=str(actual_run_id),
                        processor=result.processor,
                        missing_count=result.summary.missing_transactions_count,
                        discrepancy_amount=float(result.summary.total_discrepancy_amount)
                    )
                    
                    return str(actual_run_id)
                    
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(
                    "Failed to store reconciliation result",
                    processor=result.processor,
                    error=str(e),
                    error_code=e.pgcode if hasattr(e, 'pgcode') else None
                )
                raise
                
            except Exception as e:
                conn.rollback()
                logger.error("Unexpected error storing reconciliation result", error=str(e))
                raise

    def _bulk_insert_missing_transactions(self, cursor, run_id: str, transactions: List[Transaction]):
        """Efficiently insert missing transactions using execute_values."""
        
        # Validate transaction data before insert
        validated_transactions = []
        for txn in transactions:
            if self._validate_transaction(txn):
                validated_transactions.append((
                    str(uuid.uuid4()),  # Generate UUID for each transaction
                    run_id,
                    txn.transaction_id,
                    txn.processor_name,
                    txn.amount,
                    txn.currency,
                    txn.merchant_id,
                    txn.transaction_date,
                    txn.reference_number,
                    txn.fee,
                    'completed',  # Default status
                    json.dumps({  # metadata as JSONB
                        'source': 'reconciliation_engine',
                        'validation_passed': True
                    })
                ))
        
        if not validated_transactions:
            logger.warning("No valid transactions to insert", run_id=run_id)
            return
        
        query = """
            INSERT INTO missing_transactions (
                id, reconciliation_run_id, transaction_id, processor_name,
                amount, currency, merchant_id, transaction_date,
                reference_number, fee, status, metadata
            ) VALUES %s
        """
        
        execute_values(
            cursor, query, validated_transactions,
            template=None, page_size=1000  # Process in batches for large datasets
        )
        
        logger.info(
            "Bulk inserted missing transactions",
            count=len(validated_transactions),
            run_id=run_id
        )

    def _validate_transaction(self, txn: Transaction) -> bool:
        """Validate transaction data against business rules."""
        
        try:
            # Basic validation
            if not txn.transaction_id or not txn.transaction_id.strip():
                logger.warning("Invalid transaction: empty transaction_id")
                return False
                
            if not txn.processor_name or not txn.processor_name.strip():
                logger.warning("Invalid transaction: empty processor_name", txn_id=txn.transaction_id)
                return False
                
            if txn.amount <= 0:
                logger.warning("Invalid transaction: non-positive amount", txn_id=txn.transaction_id, amount=txn.amount)
                return False
                
            if len(txn.currency) != 3 or not txn.currency.isupper():
                logger.warning("Invalid transaction: invalid currency code", txn_id=txn.transaction_id, currency=txn.currency)
                return False
                
            # Date validation
            if txn.transaction_date > datetime.utcnow():
                logger.warning("Invalid transaction: future date", txn_id=txn.transaction_id)
                return False
                
            # Fee validation
            if txn.fee and txn.fee > txn.amount * Decimal('0.5'):
                logger.warning("Invalid transaction: excessive fee", txn_id=txn.transaction_id, fee=txn.fee, amount=txn.amount)
                return False
                
            return True
            
        except Exception as e:
            logger.warning("Transaction validation failed", txn_id=getattr(txn, 'transaction_id', 'unknown'), error=str(e))
            return False

    def _perform_data_quality_checks(self, cursor, run_id: str, result: ReconciliationResult):
        """Perform data quality validations and store results."""
        
        checks = []
        
        # Check 1: Verify totals match detail records
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(amount), 0)
            FROM missing_transactions 
            WHERE reconciliation_run_id = %s
        """, (run_id,))
        
        actual_count, actual_amount = cursor.fetchone()
        
        count_check_passed = actual_count == result.summary.missing_transactions_count
        amount_check_passed = abs(float(actual_amount) - float(result.summary.total_discrepancy_amount)) <= 0.01
        
        checks.extend([
            {
                'check_name': 'missing_transaction_count_validation',
                'check_result': count_check_passed,
                'check_details': {
                    'expected_count': result.summary.missing_transactions_count,
                    'actual_count': actual_count
                },
                'severity': 'error' if not count_check_passed else 'info'
            },
            {
                'check_name': 'total_discrepancy_amount_validation', 
                'check_result': amount_check_passed,
                'check_details': {
                    'expected_amount': float(result.summary.total_discrepancy_amount),
                    'actual_amount': float(actual_amount),
                    'difference': abs(float(actual_amount) - float(result.summary.total_discrepancy_amount))
                },
                'severity': 'error' if not amount_check_passed else 'info'
            }
        ])
        
        # Check 2: Business logic validation
        success_rate = self._calculate_success_rate(result)
        high_discrepancy = result.summary.total_discrepancy_amount > Decimal('10000')
        
        checks.append({
            'check_name': 'high_discrepancy_alert',
            'check_result': not high_discrepancy,
            'check_details': {
                'discrepancy_amount': float(result.summary.total_discrepancy_amount),
                'threshold': 10000.0,
                'success_rate': success_rate
            },
            'severity': 'critical' if high_discrepancy else 'info'
        })
        
        # Store data quality check results
        for check in checks:
            cursor.execute("""
                INSERT INTO data_quality_checks (
                    id, reconciliation_run_id, check_name, check_result, 
                    check_details, severity
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()),
                run_id,
                check['check_name'],
                check['check_result'],
                json.dumps(check['check_details']),
                check['severity']
            ))

    def _calculate_success_rate(self, result: ReconciliationResult) -> float:
        """Calculate reconciliation success rate as percentage."""
        if result.summary.processor_transactions == 0:
            return 100.0
        return ((result.summary.processor_transactions - result.summary.missing_transactions_count) 
                / result.summary.processor_transactions) * 100

    def _log_audit_event(self, cursor, action: str, table_name: str = None, 
                        record_id: str = None, old_values: Dict[str, Any] = None, 
                        new_values: Dict[str, Any] = None):
        """Log comprehensive audit event with JSONB support."""
        
        cursor.execute("""
            INSERT INTO audit_log (
                id, action, table_name, record_id, old_values, new_values,
                user_id, application_name
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            str(uuid.uuid4()),
            action,
            table_name,
            record_id,
            json.dumps(old_values or {}),
            json.dumps(new_values or {}),
            os.getenv('USER', 'system'),
            'fintech_reconciliation_system'
        ))

    def update_s3_report_key(self, run_id: str, s3_key: str):
        """Update S3 report key for a reconciliation run."""
        
        with self.get_connection() as conn:
            if conn is None:
                return
                
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE reconciliation_runs 
                    SET report_s3_key = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (s3_key, run_id))
                
                conn.commit()
                logger.info("Updated S3 report key", run_id=run_id, s3_key=s3_key)

    def health_check(self) -> bool:
        """Comprehensive database health check."""
        
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return False
                    
                with conn.cursor() as cursor:
                    # Test basic connectivity
                    cursor.execute("SELECT 1")
                    
                    # Test table access
                    cursor.execute("SELECT COUNT(*) FROM reconciliation_runs")
                    
                    # Record health check
                    cursor.execute("""
                        INSERT INTO system_health (
                            id, component, status, response_time_ms, metrics
                        ) VALUES (%s, %s, %s, %s, %s)
                    """, (
                        str(uuid.uuid4()),
                        'database_manager',
                        'healthy',
                        50,  # Mock response time
                        json.dumps({'connection_test': 'passed', 'table_access': 'passed'})
                    ))
                    
                    conn.commit()
                    return True
                    
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False

    def get_reconciliation_history(self, processor: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get reconciliation history for monitoring and trends."""
        
        with self.get_connection() as conn:
            if conn is None:
                return []
                
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM v_recent_reconciliations 
                    WHERE processor_name = %s 
                    AND run_date >= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY run_date DESC
                """, (processor, days))
                
                return [dict(row) for row in cursor.fetchall()]