import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Any, Dict
from pathlib import Path

from pydantic import BaseModel, Field, BaseSettings

# --- 1. System Configuration (DevOps Best Practice) ---
class Settings(BaseSettings):
    """Centralized, typed application settings loaded from environment."""
    DB_URL: str = Field(..., description="PostgreSQL database connection string.")
    AWS_BUCKET_NAME: str = Field('reconciliation-reports-bucket', description="S3 bucket for storage.")
    REPORT_OUTPUT_DIR: Path = Path("local_reports")
    OPS_EMAIL_RECIPIENT: str = 'operations@fintech.com'

    class Config:
        env_file = ".env"

# --- 2. Core Transaction Data (Financial Precision) ---
class Transaction(BaseModel):
    """Pydantic schema for transaction data, ensuring Decimal precision."""
    transaction_id: str = Field(..., description="Unique transaction identifier")
    processor_name: str = Field(..., description="Payment processor name")
    amount: Decimal = Field(..., decimal_places=2, description="Transaction amount") 
    currency: str = Field(default='USD', description="Transaction currency")
    status: str = Field(..., description="Transaction status")
    merchant_id: str = Field(..., description="Merchant identifier")
    transaction_date: datetime = Field(..., description="When transaction occurred")
    reference_number: Optional[str] = Field(None, description="External reference number")
    fee: Optional[Decimal] = Field(default=Decimal('0.00'), decimal_places=2, description="Processing fee")

    class Config:
        # Allow field population by both attribute name and alias
        populate_by_name = True

# --- 3. Reconciliation Models ---
class ReconciliationSummary(BaseModel):
    processor: str = Field(..., description="Payment processor name")
    date: date = Field(..., description="Reconciliation date")
    processor_transactions: int = Field(..., description="Number of processor transactions")
    internal_transactions: int = Field(..., description="Number of internal transactions")
    missing_transactions_count: int = Field(..., description="Number of missing transactions")
    total_discrepancy_amount: Decimal = Field(default=Decimal('0.00'), decimal_places=2, description="Total amount of discrepancies")

class ReconciliationResult(BaseModel):
    """The complete output of the ReconciliationEngine."""
    processor: str = Field(..., description="Payment processor name")
    date: date = Field(..., description="Reconciliation date")
    summary: ReconciliationSummary = Field(..., description="Summary statistics")
    missing_transactions_details: List[Transaction] = Field(default_factory=list, description="Detailed list of missing transactions")

# --- 4. Report Contracts (Clean Interface) ---
class ReportBundle(BaseModel):
    """Consolidates the output of the ReportGenerator."""
    csv_path: Path = Field(..., description="Path to CSV report")
    json_path: Path = Field(..., description="Path to JSON report")
    executive_summary_text: str = Field(..., description="Executive summary text")
    s3_key_or_path: Optional[str] = Field(None, description="S3 key or local path")
    presigned_url: Optional[str] = Field(None, description="S3 presigned URL")

# --- 5. Database Models (Audit & Compliance) ---
class ReconciliationRun(BaseModel):
    """Model for the primary audit table."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    target_date: date = Field(..., description="Date being reconciled")
    processor: str = Field(..., description="Payment processor name")
    status: str = Field(default='running', description="Run status")
    start_time: datetime = Field(default_factory=datetime.utcnow)
    processor_transaction_count: Optional[int] = Field(None, description="Number of processor transactions")
    missing_transaction_count: Optional[int] = Field(None, description="Number of missing transactions")
    total_discrepancy_amount: Optional[Decimal] = Field(None, decimal_places=2, description="Total discrepancy amount")
    report_s3_key: Optional[str] = Field(None, description="S3 key for the report")

class AuditLog(BaseModel):
    """Model for the granular audit log table."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str = Field(..., description="Type of event")
    table_name: str = Field(..., description="Affected table name")
    record_id: Optional[uuid.UUID] = Field(None, description="Affected record ID")
    old_values: Dict[str, Any] = Field(default_factory=dict, description="Previous values")
    new_values: Dict[str, Any] = Field(default_factory=dict, description="New values")