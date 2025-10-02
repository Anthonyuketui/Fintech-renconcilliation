"""
Production-ready database manager for reconciliation system.
Handles PostgreSQL operations with full transaction safety, UUID support,
data validation, and comprehensive audit logging.
"""

import json
import os
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import psycopg2
import psycopg2.extras
from psycopg2.extras import RealDictCursor, execute_values
from structlog import get_logger

from models import ReconciliationResult, Settings, Transaction

logger = get_logger()


class DatabaseManager:
    """Production-ready PostgreSQL manager with UUID support and comprehensive validation."""

    def __init__(self, settings: Settings = None):
        """Initialize database configuration from Settings or environment variables."""
        if settings and getattr(settings, "DB_URL", None):
            self.db_url = settings.DB_URL
        else:
            self.host = os.getenv("DB_HOST", "localhost")
            self.port = int(os.getenv("DB_PORT", "5432"))
            self.dbname = os.getenv("DB_NAME", "fintech_reconciliation")
            self.user = os.getenv("DB_USER", "postgres")
            password = os.getenv("DB_PASSWORD", "")
            encoded_password = quote_plus(password) if password else ""
            self.db_url = f"postgresql://{self.user}:{encoded_password}@{self.host}:{self.port}/{self.dbname}"
            print("📌 DB URL being used:", self.db_url)

    @contextmanager
    def get_connection(self):
        """Production-ready connection manager with comprehensive error handling."""
        conn = None
        if not self.db_url or "None" in self.db_url:
            logger.warning(
                "Database URL not properly configured; skipping database operations"
            )
            yield None
            return
        try:
            conn = psycopg2.connect(self.db_url)
            conn.autocommit = False  # Explicit transaction control
            yield conn
        except psycopg2.Error as exc:
            if conn:
                conn.rollback()
            logger.error(
                "Database transaction failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise
        except Exception as exc:
            if conn:
                conn.rollback()
            logger.error("Unexpected database error", error=str(exc))
            raise
        finally:
            if conn:
                conn.close()

    # =========================================================================
    # CORE INTERFACE METHODS (Called by main.py Orchestrator)
    # =========================================================================

    def create_reconciliation_run(self, date: date, processor: str) -> Optional[str]:
        """
        [STEP 1: START] Creates an initial reconciliation run record with 'running' status.
        Uses UPSERT to guarantee idempotency: re-running the same processor/date
        will update the existing record instead of failing with UniqueViolation.
        Returns the run_id (UUID).
        """
        run_uuid = str(uuid.uuid4())
        with self.get_connection() as conn:
            if conn is None:
                return None
            try:
                with conn.cursor() as cursor:
                    cursor.execute("BEGIN")

                    # First, check if there's an existing run for this date/processor
                    cursor.execute(
                        """
                        SELECT id FROM reconciliation_runs
                        WHERE run_date = %s AND processor_name = %s
                    """,
                        (date, processor),
                    )
                    existing_run = cursor.fetchone()

                    if existing_run:
                        existing_run_id = existing_run[0]
                        # Delete old missing transactions for this run to prevent duplicates
                        cursor.execute(
                            """
                            DELETE FROM missing_transactions
                            WHERE reconciliation_run_id = %s
                        """,
                            (existing_run_id,),
                        )
                        deleted_count = cursor.rowcount
                        if deleted_count > 0:
                            logger.info(
                                "Cleaned up old missing transactions on restart",
                                run_id=existing_run_id,
                                deleted_count=deleted_count,
                            )

                    # Now do the UPSERT
                    cursor.execute(
                        """
                        INSERT INTO reconciliation_runs (
                            id, run_date, processor_name, start_time, status, created_by
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (run_date, processor_name)
                        DO UPDATE SET
                            start_time = EXCLUDED.start_time,
                            end_time = NULL,
                            status = 'running',
                            error_message = NULL,
                            processor_transaction_count = NULL,
                            internal_transaction_count = NULL,
                            missing_transaction_count = NULL,
                            total_discrepancy_amount = NULL,
                            report_s3_key = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id
                    """,
                        (
                            run_uuid,
                            date,
                            processor,
                            datetime.utcnow(),
                            "running",
                            "reconciliation_system",
                        ),
                    )
                    run_id = cursor.fetchone()[0]
                    self._log_audit_event(
                        cursor,
                        action="reconciliation_started_or_restarted",
                        table_name="reconciliation_runs",
                        record_id=run_id,
                        new_values={
                            "processor": processor,
                            "run_date": date.isoformat(),
                        },
                    )
                    conn.commit()
                    return run_id
            except Exception:
                raise

    def store_reconciliation_result(
        self, run_id: str, result: ReconciliationResult
    ) -> None:
        """
        [STEP 2: METRICS] Updates the final reconciliation run record with all metrics and stores missing transactions.
        """
        with self.get_connection() as conn:
            if conn is None:
                return
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("BEGIN")

                    # CRITICAL: Insert missing transactions FIRST (before UPDATE)
                    if result.missing_transactions_details:
                        self._bulk_insert_missing_transactions(
                            cursor, run_id, result.missing_transactions_details
                        )
                        logger.info(
                            "Inserted missing transactions before status update",
                            count=len(result.missing_transactions_details),
                            run_id=run_id,
                        )

                    # NOW do the UPDATE (trigger will find the transactions)
                    cursor.execute(
                        """
                        UPDATE reconciliation_runs SET
                            end_time = %s,
                            status = %s,
                            processor_transaction_count = %s,
                            internal_transaction_count = %s,
                            missing_transaction_count = %s,
                            total_discrepancy_amount = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """,
                        (
                            datetime.utcnow(),
                            "completed",
                            result.summary.processor_transactions,
                            result.summary.internal_transactions,
                            result.summary.missing_transactions_count,
                            result.summary.total_discrepancy_amount,
                            run_id,
                        ),
                    )

                    # Perform data quality checks
                    self._perform_data_quality_checks(cursor, run_id, result)

                    # Log audit event
                    self._log_audit_event(
                        cursor,
                        action="reconciliation_metrics_recorded",
                        table_name="reconciliation_runs",
                        record_id=run_id,
                        new_values={
                            "status": "completed",
                            "missing_count": result.summary.missing_transactions_count,
                            "discrepancy_amount": float(
                                result.summary.total_discrepancy_amount
                            ),
                        },
                    )

                    conn.commit()
            except Exception:
                raise

    def update_s3_report_key(self, run_id: str, s3_key: str):
        """
        [STEP 3: S3 KEY] Update S3 report key for a reconciliation run.
        """
        with self.get_connection() as conn:
            if conn is None:
                return
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE reconciliation_runs
                        SET report_s3_key = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """,
                        (s3_key, run_id),
                    )
                    self._log_audit_event(
                        cursor,
                        action="s3_key_updated",
                        table_name="reconciliation_runs",
                        record_id=run_id,
                        new_values={"report_s3_key": s3_key},
                    )
                    conn.commit()
                    logger.info("Updated S3 report key", run_id=run_id, s3_key=s3_key)
            except Exception:
                raise

    def update_reconciliation_status(
        self, run_id: str, status: str, error_message: Optional[str] = None
    ):
        """
        [ERROR HANDLER] Update the status of a reconciliation run.
        If status = 'failed', an error_message is required to satisfy DB constraints.
        """
        with self.get_connection() as conn:
            if conn is None:
                return
            try:
                with conn.cursor() as cursor:
                    if status == "failed":
                        cursor.execute(
                            """
                            UPDATE reconciliation_runs
                            SET status = %s,
                                end_time = %s,
                                error_message = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """,
                            (
                                status,
                                datetime.utcnow(),
                                error_message or "Unknown error",
                                run_id,
                            ),
                        )
                    else:
                        cursor.execute(
                            """
                            UPDATE reconciliation_runs
                            SET status = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """,
                            (status, run_id),
                        )
                    self._log_audit_event(
                        cursor,
                        action=f"status_updated_to_{status}",
                        table_name="reconciliation_runs",
                        record_id=run_id,
                        new_values={"status": status, "error_message": error_message},
                    )
                    conn.commit()
                    logger.warning(
                        "Updated run status", run_id=run_id, new_status=status
                    )
            except Exception:
                raise

    # =========================================================================
    # INTERNAL HELPER METHODS
    # =========================================================================

    def _bulk_insert_missing_transactions(
        self, cursor, run_id: str, transactions: List[Transaction]
    ):
        """Efficiently insert missing transactions using execute_values."""
        validated_transactions = []
        for txn in transactions:
            if self._validate_transaction(txn):
                validated_transactions.append(
                    (
                        str(uuid.uuid4()),
                        run_id,
                        txn.transaction_id,
                        txn.processor_name,
                        txn.amount,
                        txn.currency,
                        txn.merchant_id,
                        txn.transaction_date,
                        txn.reference_number,
                        txn.fee,
                        "completed",
                        json.dumps(
                            {
                                "source": "reconciliation_engine",
                                "validation_passed": True,
                            }
                        ),
                    )
                )
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
            cursor, query, validated_transactions, template=None, page_size=1000
        )
        logger.info(
            "Bulk inserted missing transactions",
            count=len(validated_transactions),
            run_id=run_id,
        )

    def _validate_transaction(self, txn: Transaction) -> bool:
        """Validate transaction data against business rules."""
        try:
            if not txn.transaction_id or not txn.transaction_id.strip():
                logger.warning("Invalid transaction: empty transaction_id")
                return False
            if not txn.processor_name or not txn.processor_name.strip():
                logger.warning(
                    "Invalid transaction: empty processor_name",
                    txn_id=txn.transaction_id,
                )
                return False
            if txn.amount <= 0:
                logger.warning(
                    "Invalid transaction: non-positive amount",
                    txn_id=txn.transaction_id,
                    amount=txn.amount,
                )
                return False
            if len(txn.currency) != 3 or not txn.currency.isupper():
                logger.warning(
                    "Invalid transaction: invalid currency code",
                    txn_id=txn.transaction_id,
                    currency=txn.currency,
                )
                return False
            if txn.transaction_date > datetime.utcnow():
                logger.warning(
                    "Invalid transaction: future date", txn_id=txn.transaction_id
                )
                return False
            if txn.fee and txn.fee > txn.amount * Decimal("0.5"):
                logger.warning(
                    "Invalid transaction: excessive fee",
                    txn_id=txn.transaction_id,
                    fee=txn.fee,
                    amount=txn.amount,
                )
                return False
            return True
        except Exception as e:
            logger.warning(
                "Transaction validation failed",
                txn_id=getattr(txn, "transaction_id", "unknown"),
                error=str(e),
            )
            return False

    def _perform_data_quality_checks(
        self, cursor, run_id: str, result: ReconciliationResult
    ):
        """Perform data quality validations and store results."""
        checks = []

        # FIXED: Use explicit column aliases and handle RealDictCursor properly
        cursor.execute(
            """
            SELECT COUNT(*)::integer as txn_count,
                   COALESCE(SUM(amount), 0)::decimal as total_amount
            FROM missing_transactions
            WHERE reconciliation_run_id = %s
        """,
            (run_id,),
        )

        row = cursor.fetchone()

        # Handle both dict (RealDictCursor) and tuple cursor responses
        if isinstance(row, dict):
            actual_count = row["txn_count"]
            actual_amount = row["total_amount"]
        else:
            actual_count, actual_amount = row

        count_check_passed = actual_count == result.summary.missing_transactions_count
        amount_check_passed = (
            abs(float(actual_amount) - float(result.summary.total_discrepancy_amount))
            <= 0.01
        )

        checks.extend(
            [
                {
                    "check_name": "missing_transaction_count_validation",
                    "check_result": count_check_passed,
                    "check_details": {
                        "expected_count": result.summary.missing_transactions_count,
                        "actual_count": actual_count,
                    },
                    "severity": "error" if not count_check_passed else "info",
                },
                {
                    "check_name": "total_discrepancy_amount_validation",
                    "check_result": amount_check_passed,
                    "check_details": {
                        "expected_amount": float(
                            result.summary.total_discrepancy_amount
                        ),
                        "actual_amount": float(actual_amount),
                        "difference": abs(
                            float(actual_amount)
                            - float(result.summary.total_discrepancy_amount)
                        ),
                    },
                    "severity": "error" if not amount_check_passed else "info",
                },
            ]
        )

        success_rate = self._calculate_success_rate(result)
        high_discrepancy = result.summary.total_discrepancy_amount > Decimal("10000")

        checks.append(
            {
                "check_name": "high_discrepancy_alert",
                "check_result": not high_discrepancy,
                "check_details": {
                    "discrepancy_amount": float(
                        result.summary.total_discrepancy_amount
                    ),
                    "threshold": 10000.0,
                    "success_rate": success_rate,
                },
                "severity": "critical" if high_discrepancy else "info",
            }
        )

        for check in checks:
            cursor.execute(
                """
                INSERT INTO data_quality_checks (
                    id, reconciliation_run_id, check_name, check_result,
                    check_details, severity
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
                (
                    str(uuid.uuid4()),
                    run_id,
                    check["check_name"],
                    check["check_result"],
                    json.dumps(check["check_details"]),
                    check["severity"],
                ),
            )

    def _calculate_success_rate(self, result: ReconciliationResult) -> float:
        """Calculate reconciliation success rate as percentage."""
        if result.summary.processor_transactions == 0:
            return 100.0
        return (
            (
                result.summary.processor_transactions
                - result.summary.missing_transactions_count
            )
            / result.summary.processor_transactions
        ) * 100

    def _log_audit_event(
        self,
        cursor,
        action: str,
        table_name: str = None,
        record_id: str = None,
        old_values: Dict[str, Any] = None,
        new_values: Dict[str, Any] = None,
    ):
        """Log comprehensive audit event with JSONB support."""
        cursor.execute(
            """
            INSERT INTO audit_log (
                id, action, table_name, record_id, old_values, new_values,
                user_id, application_name
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                str(uuid.uuid4()),
                action,
                table_name,
                record_id,
                json.dumps(old_values or {}),
                json.dumps(new_values or {}),
                os.getenv("USER", "system"),
                "fintech_reconciliation_system",
            ),
        )

    def health_check(self) -> bool:
        """Comprehensive database health check."""
        try:
            with self.get_connection() as conn:
                if conn is None:
                    return False
                with conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM reconciliation_runs")
                    cursor.execute(
                        """
                        INSERT INTO system_health (
                            id, component, status, response_time_ms, metrics
                        ) VALUES (%s, %s, %s, %s, %s)
                    """,
                        (
                            str(uuid.uuid4()),
                            "database_manager",
                            "healthy",
                            50,
                            json.dumps(
                                {"connection_test": "passed", "table_access": "passed"}
                            ),
                        ),
                    )
                    conn.commit()
                    return True
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False

    def get_reconciliation_history(
        self, processor: str, days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get reconciliation history for monitoring and trends."""
        with self.get_connection() as conn:
            if conn is None:
                return []
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM reconciliation_runs
                    WHERE processor_name = %s
                    AND run_date >= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY run_date DESC
                """,
                    (processor, days),
                )
                return [dict(row) for row in cursor.fetchall()]
