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

# --- 2. Core Transaction Data (Financial Precision) ---
class Transaction(BaseModel):
    """Pydantic schema for transaction data, ensuring Decimal precision."""
    id: str
    processor_id: str
    amount: Decimal = Field(..., decimal_places=2) 
    currency: str = 'USD'
    status: str
    transaction_date: datetime
    fee: Decimal = Decimal('0.00')

# --- 3. Reconciliation Models ---
class ReconciliationSummary(BaseModel):
    processor: str
    date: date
    processor_transactions: int
    internal_transactions: int
    missing_transactions_count: int
    total_discrepancy_amount: Decimal = Decimal('0.00')

class ReconciliationResult(BaseModel):
    """The complete output of the ReconciliationEngine."""
    processor: str
    date: date
    summary: ReconciliationSummary
    missing_transactions: List[Transaction] = Field(default_factory=list)

# --- 4. Report Contracts (Clean Interface) ---
class ReportBundle(BaseModel):
    """Consolidates the output of the ReportGenerator."""
    csv_path: Path 
    json_path: Path 
    executive_summary_text: str 
    s3_key_or_path: Optional[str] = None
    presigned_url: Optional[str] = None 

# --- 5. Database Models (Audit & Compliance) ---
class ReconciliationRun(BaseModel):
    """Model for the primary audit table."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    target_date: date
    processor: str
    status: str = 'running'
    start_time: datetime = Field(default_factory=datetime.utcnow)
    processor_transaction_count: Optional[int] = None
    missing_transaction_count: Optional[int] = None
    total_discrepancy_amount: Optional[Decimal] = None
    report_s3_key: Optional[str] = None

class AuditLog(BaseModel):
    """Model for the granular audit log table."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str
    table_name: str
    record_id: Optional[uuid.UUID] = None
    old_values: Dict[str, Any] = Field(default_factory=dict)
    new_values: Dict[str, Any] = Field(default_factory=dict)