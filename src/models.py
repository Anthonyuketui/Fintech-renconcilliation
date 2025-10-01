"""
models.py

Defines all core data models for the FinTech Transaction Reconciliation System.
Models are built using Pydantic for robust validation, type safety, and serialization.
These models serve as the backbone for all business logic, API contracts, and reporting.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Any, Dict
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# -----------------------------------------------------------------------------
# 1. System Configuration Model
# -----------------------------------------------------------------------------
class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables or .env files.

    This model centralizes all settings for database, API endpoints, AWS, and reporting.
    """
    # Example fields (add your actual config fields here)
    DB_URL: Optional[str] = Field(None, description="Database connection URL")
    AWS_BUCKET_NAME: Optional[str] = Field(None, description="AWS S3 bucket name")
    AWS_REGION: Optional[str] = Field(None, description="AWS region")
    PROCESSOR_API_BASE_URL: Optional[str] = Field(None, description="Base URL for processor API")
    INTERNAL_API_BASE_URL: Optional[str] = Field(None, description="Base URL for internal API")
    REPORT_OUTPUT_DIR: Path = Field(default=Path("local_reports"), description="Directory for report outputs")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# -----------------------------------------------------------------------------
# 2. Core Transaction Data Model
# -----------------------------------------------------------------------------
class Transaction(BaseModel):
    """
    Represents a single financial transaction.

    All monetary fields use Decimal for precision. This model is used for both
    processor and internal transactions, ensuring a unified schema for reconciliation.
    """
    transaction_id: str = Field(..., description="Unique transaction identifier")
    processor_name: str = Field(..., description="Name of the payment processor")
    amount: Decimal = Field(..., description="Transaction amount in currency units")
    currency: str = Field(..., description="ISO currency code (e.g., USD)")
    status: str = Field(..., description="Transaction status (e.g., completed, pending)")
    merchant_id: str = Field(..., description="Merchant identifier")
    transaction_date: datetime = Field(..., description="Timestamp of the transaction")
    reference_number: str = Field(..., description="Reference number for reconciliation")
    fee: Decimal = Field(..., description="Transaction fee charged by processor")

# -----------------------------------------------------------------------------
# 3. Reconciliation Models
# -----------------------------------------------------------------------------
class ReconciliationSummary(BaseModel):
    """
    Summary statistics from a reconciliation process.

    Captures high-level metrics for reporting and audit.
    """
    reconciliation_date: date = Field(..., description="Date of reconciliation run")
    processor: str = Field(..., description="Payment processor name")
    processor_transactions: int = Field(..., description="Number of processor transactions")
    internal_transactions: int = Field(..., description="Number of internal transactions")
    missing_transactions_count: int = Field(..., description="Number of missing transactions")
    total_discrepancy_amount: Decimal = Field(
        default=Decimal('0.00'),
        description="Total amount of discrepancies"
    )
    total_volume_processed: Decimal = Field(
        default=Decimal('0.00'),
        description="Total financial volume processed"
    )

class ReconciliationResult(BaseModel):
    """
    Detailed output of a reconciliation run.

    Includes summary metrics and a list of missing transactions for further analysis.
    """
    reconciliation_date: date = Field(..., description="Date of reconciliation run")
    processor: str = Field(..., description="Payment processor name")
    summary: ReconciliationSummary = Field(..., description="Summary statistics")
    missing_transactions_details: List[Transaction] = Field(
        default_factory=list,
        description="List of transactions missing from internal records"
    )

# -----------------------------------------------------------------------------
# 4. Report Contracts
# -----------------------------------------------------------------------------
class ReportBundle(BaseModel):
    """
    Encapsulates all generated reports for a reconciliation run.

    Used for packaging CSV, JSON, and executive summaries for archival and distribution.
    """
    csv_path: Path = Field(..., description="Path to detailed CSV report")
    json_path: Path = Field(..., description="Path to JSON report")
    summary_text: str = Field(..., description="Executive summary text")

# -----------------------------------------------------------------------------
# 5. Database Models (Audit & Compliance)
# -----------------------------------------------------------------------------
class ReconciliationRun(BaseModel):
    """
    Represents a reconciliation run record in the database.

    Used for audit logging, compliance, and historical analysis.
    """
    id: str = Field(..., description="Unique run identifier (UUID)")
    run_date: date = Field(..., description="Date of reconciliation run")
    processor_name: str = Field(..., description="Payment processor name")
    start_time: datetime = Field(..., description="Timestamp when run started")
    end_time: Optional[datetime] = Field(None, description="Timestamp when run ended")
    status: str = Field(..., description="Run status (running, completed, failed)")
    created_by: str = Field(..., description="User or system that initiated the run")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    report_s3_key: Optional[str] = Field(None, description="S3 key for archived report")
    error_message: Optional[str] = Field(None, description="Error message if run failed")

class AuditLog(BaseModel):
    """
    Represents an audit log entry for database operations.

    Ensures traceability and compliance for all changes to reconciliation data.
    """
    id: str = Field(..., description="Unique audit log identifier (UUID)")
    action: str = Field(..., description="Action performed (e.g., reconciliation_started)")
    table_name: str = Field(..., description="Affected table name")
    record_id: str = Field(..., description="ID of affected record")
    old_values: Dict[str, Any] = Field(default_factory=dict, description="Values before change")
    new_values: Dict[str, Any] = Field(default_factory=dict, description="Values after change")
    user_id: str = Field(..., description="User who performed the action")
    application_name: str = Field(..., description="Application name")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Time of action")