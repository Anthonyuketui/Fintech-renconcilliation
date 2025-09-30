# models.py - CORRECTED VERSION
"""
Pydantic models for the FinTech Reconciliation System.
Uses Pydantic V2 syntax and includes all required configuration fields.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Any, Dict
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# --- 1. System Configuration (DevOps Best Practice) ---
class Settings(BaseSettings):
    """Centralized, typed application settings loaded from environment."""
    
    # Database Configuration
    DB_HOST: str = Field(default="localhost", description="Database host")
    DB_PORT: int = Field(default=5432, description="Database port")
    DB_NAME: str = Field(default="fintech_reconciliation", description="Database name")
    DB_USER: str = Field(default="postgres", description="Database user")
    DB_PASSWORD: str = Field(default="", description="Database password")
    DB_URL: Optional[str] = Field(default=None, description="Complete database URL (overrides individual params)")
    
    # AWS Configuration
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, description="AWS access key")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, description="AWS secret key")
    AWS_BUCKET_NAME: str = Field(default='fintech-reconciliation-reports', description="S3 bucket name")
    AWS_REGION: str = Field(default='us-east-1', description="AWS region")
    
    # API Configuration - ADDED THESE MISSING FIELDS
    PROCESSOR_API_BASE_URL: str = Field(
        default="https://dummyjson.com",
        description="Payment processor API base URL"
    )
    INTERNAL_API_BASE_URL: str = Field(
        default="https://jsonplaceholder.typicode.com",
        description="Internal FinTech API base URL"
    )
    
    # Email Configuration
    SMTP_SERVER: str = Field(default="smtp.gmail.com", description="SMTP server")
    SMTP_PORT: int = Field(default=587, description="SMTP port")
    EMAIL_USER: Optional[str] = Field(default=None, description="Email username")
    EMAIL_PASSWORD: Optional[str] = Field(default=None, description="Email password")
    OPERATIONS_EMAIL: str = Field(
        default='operations@fintech.com',
        description="Operations team email"
    )
    
    # Application Configuration
    REPORT_OUTPUT_DIR: Path = Field(
        default=Path("local_reports"),
        description="Directory for local report storage"
    )
    
    # Pydantic V2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )
    
    def get_db_url(self) -> str:
        """Construct database URL if not explicitly provided."""
        if self.DB_URL:
            return self.DB_URL
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


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

    model_config = {"populate_by_name": True}


# --- 3. Reconciliation Models ---
class ReconciliationSummary(BaseModel):
    """Summary statistics from reconciliation process."""
    processor: str = Field(..., description="Payment processor name")
    reconciliation_date: date = Field(..., description="Reconciliation date")
    processor_transactions: int = Field(..., description="Number of processor transactions")
    internal_transactions: int = Field(..., description="Number of internal transactions")
    missing_transactions_count: int = Field(..., description="Number of missing transactions")
    total_discrepancy_amount: Decimal = Field(
        default=Decimal('0.00'),
        decimal_places=2,
        description="Total amount of discrepancies"
    )
    total_volume_processed: Decimal = Field(
        default=Decimal('0.00'),
        decimal_places=2,
        description="Total financial volume processed"
    )


class ReconciliationResult(BaseModel):
    """The complete output of the ReconciliationEngine."""
    processor: str = Field(..., description="Payment processor name")
    reconciliation_date: date = Field(..., description="Reconciliation date")
    summary: ReconciliationSummary = Field(..., description="Summary statistics")
    missing_transactions_details: List[Transaction] = Field(
        default_factory=list,
        description="Detailed list of missing transactions"
    )


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
    total_discrepancy_amount: Optional[Decimal] = Field(
        None,
        decimal_places=2,
        description="Total discrepancy amount"
    )
    report_s3_key: Optional[str] = Field(None, description="S3 key for the report")


class AuditLog(BaseModel):
    """Model for the granular audit log table."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str = Field(..., description="Type of event")
    table_name: str = Field(..., description="Affected table name")
    record_id: Optional[uuid.UUID] = Field(None, description="Affected record ID")
    old_values: Dict[str, Any] = Field(default_factory=dict, description="Previous values")
    new_values: Dict[str, Any] = Field(default_factory=dict, description="New values")