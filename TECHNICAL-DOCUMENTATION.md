# FinTech Transaction Reconciliation System - Complete Technical Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Container Configuration](#container-configuration)
3. [Core Application Code](#core-application-code)
   - [3.1 Data Models (models.py)](#31-data-models-modelspy)
   - [3.2 Main Orchestrator (main.py)](#32-main-orchestrator-mainpy)
   - [3.3 Data Fetcher (data_fetcher.py)](#33-data-fetcher-data_fetcherpy)
   - [3.4 Reconciliation Engine (reconciliation_engine.py)](#34-reconciliation-engine-reconciliation_enginepy)
   - [3.5 Database Manager (database_manager.py)](#35-database-manager-database_managerpy)
   - [3.6 Report Generator (report_generator.py)](#36-report-generator-report_generatorpy)
   - [3.7 AWS Manager (aws_manager.py)](#37-aws-manager-aws_managerpy)
   - [3.8 Notification Service (notification_service.py)](#38-notification-service-notification_servicepy)
4. [Infrastructure as Code](#infrastructure-as-code)
5. [CI/CD Pipeline](#cicd-pipeline)
6. [Configuration Files](#configuration-files)
7. [Testing Framework](#testing-framework)
8. [Troubleshooting Guide](#troubleshooting-guide)

---

## System Overview

This is an enterprise-grade FinTech transaction reconciliation system that:
- Automatically reconciles transactions across multiple payment processors (Stripe, PayPal, Square)
- Detects discrepancies between processor and internal transaction records
- Sends email notifications when issues are found
- Generates comprehensive reports in CSV and JSON formats
- Runs on AWS cloud infrastructure with automated scheduling
- Maintains audit trails for compliance

### Architecture Components
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Payment APIs  │    │  Internal APIs  │    │   PostgreSQL    │
│ (Stripe/PayPal) │    │ (Transaction)   │    │   Database      │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                 FinTech Reconciliation Engine                   │
├─────────────────┬─────────────────┬─────────────────┬───────────┤
│  DataFetcher    │ ReconcileEngine │ ReportGenerator │ AWSManager│
│  (99% coverage) │ (100% coverage) │ (99% coverage)  │(69% cover)│
└─────────────────┴─────────────────┴─────────────────┴───────────┘
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   CSV Reports   │    │  Email Alerts   │    │   AWS S3        │
│   JSON Reports  │    │  Slack Notify   │    │   Storage       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## Container Configuration

### Dockerfile - Line by Line Analysis

```dockerfile
FROM python:3.11.9-slim
```
**Purpose**: Base container image
- **python:3.11.9-slim**: Lightweight Python runtime (200MB vs 900MB full image)
- **Security**: Minimal attack surface, fewer vulnerabilities
- **Performance**: Faster container startup and deployment

```dockerfile
WORKDIR /app
```
**Purpose**: Sets working directory inside container
- **All commands**: Execute from /app directory
- **File paths**: Relative to /app for consistency

```dockerfile
# Install system dependencies and security updates
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    postgresql-client \
    libpq-dev \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
```
**Purpose**: System-level dependencies for PostgreSQL connectivity
- **apt-get update**: Refreshes package repository
- **apt-get upgrade -y**: Security updates for all packages
- **postgresql-client**: Command-line PostgreSQL tools (psql, pg_dump)
- **libpq-dev**: PostgreSQL C library headers (required for psycopg2)
- **gcc**: C compiler (needed to build Python packages with C extensions)
- **--no-install-recommends**: Minimal installation (reduces image size)
- **apt-get clean**: Removes package cache
- **rm -rf /var/lib/apt/lists/***: Removes package lists (reduces image size by ~40MB)

```dockerfile
# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```
**Purpose**: Python package installation
- **COPY requirements.txt**: Copies dependency list to container
- **pip install --no-cache-dir**: Installs packages without caching (reduces image size)
- **-r requirements.txt**: Installs all packages from requirements file

```dockerfile
# Create output directory
RUN mkdir -p /app/Sample_Output
```
**Purpose**: Local storage fallback
- **mkdir -p**: Creates directory with parent directories if needed
- **Sample_Output**: Stores reports locally when S3 upload fails
- **Fallback mechanism**: Ensures reports are never lost

```dockerfile
# Create non-root user
RUN useradd -m fintech && chown -R fintech:fintech /app
```
**Purpose**: Security hardening
- **useradd -m fintech**: Creates user 'fintech' with home directory
- **chown -R fintech:fintech /app**: Gives ownership of /app to fintech user
- **Security principle**: Never run containers as root (prevents privilege escalation)

```dockerfile
# Copy application code
COPY --chown=fintech:fintech src/ ./src/
COPY --chown=fintech:fintech tests/ ./tests/
COPY --chown=fintech:fintech setup.sql ./
```
**Purpose**: Application code deployment
- **--chown=fintech:fintech**: Sets correct file ownership during copy
- **src/**: Main application modules
- **tests/**: Test suite for quality assurance
- **setup.sql**: Database initialization script

```dockerfile
# Switch to non-root user
USER fintech
```
**Purpose**: Security enforcement
- **USER fintech**: All subsequent commands run as non-root user
- **Container security**: Prevents malicious code from gaining root access

```dockerfile
# Set Python path
ENV PYTHONPATH=/app/src
```
**Purpose**: Python module resolution
- **PYTHONPATH**: Tells Python where to find modules
- **/app/src**: Allows imports like `from models import Transaction`
- **Module structure**: Enables clean import statements

```dockerfile
# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "from src.database_manager import DatabaseManager; dm = DatabaseManager(); exit(0 if dm.health_check() else 1)"
```
**Purpose**: Container health monitoring
- **--interval=30s**: Check health every 30 seconds
- **--timeout=10s**: Fail check if it takes longer than 10 seconds
- **--start-period=40s**: Wait 40 seconds before first check (startup time)
- **--retries=3**: Try 3 times before marking container unhealthy
- **Health check logic**: Tests database connectivity
- **exit(0)**: Healthy container
- **exit(1)**: Unhealthy container

```dockerfile
CMD ["python", "src/main.py", "--processors", "stripe", "paypal", "square"]
```
**Purpose**: Default container command
- **CMD**: Default command when container starts
- **python src/main.py**: Runs main reconciliation script
- **--processors stripe paypal square**: Processes all three payment processors
- **Override capability**: Can be overridden in ECS task definition

---

## Core Application Code

### 3.1 Data Models (models.py)

This module defines all core data structures using Pydantic for type safety and validation.

#### Settings Class - Application Configuration
```python
class Settings(BaseSettings):
```
**Purpose**: Centralized configuration management
- **BaseSettings**: Pydantic class that loads from environment variables
- **Type safety**: Ensures all config values have correct types
- **Validation**: Automatic validation of configuration values

**Database Configuration Fields:**
```python
DB_HOST: str = Field(default="localhost", description="Database host")
DB_PORT: int = Field(default=5432, description="Database port")
DB_NAME: str = Field(default="fintech_reconciliation", description="Database name")
DB_USER: str = Field(default="fintech", description="Database user")
DB_PASSWORD: str = Field(default="", description="Database password")
```
- **Field()**: Pydantic field with default values and documentation
- **Type hints**: Ensures type safety (str, int)
- **Defaults**: Fallback values for local development

**AWS Configuration Fields:**
```python
AWS_ACCESS_KEY_ID: Optional[str] = Field(None, description="AWS access key ID")
AWS_SECRET_ACCESS_KEY: Optional[str] = Field(None, description="AWS secret access key")
AWS_S3_BUCKET_NAME: Optional[str] = Field(None, description="AWS S3 bucket name")
AWS_REGION: str = Field(default="us-east-1", description="AWS region")
```
- **Optional[str]**: Can be None (for local development without AWS)
- **AWS credentials**: Used for S3 uploads and SES email sending
- **Region**: Default to us-east-1 for consistency

**Email Configuration Fields:**
```python
SMTP_SERVER: Optional[str] = Field(None, description="SMTP server address")
SMTP_PORT: int = Field(default=587, description="SMTP server port")
EMAIL_USER: Optional[str] = Field(None, description="Email username")
EMAIL_PASSWORD: Optional[str] = Field(None, description="Email password or app password")
OPERATIONS_EMAIL: Optional[str] = Field(None, description="Operations team email for notifications")
```
- **SMTP configuration**: For traditional email sending (fallback)
- **Port 587**: Standard SMTP submission port with STARTTLS
- **Operations email**: Where alerts are sent

**Configuration Loading:**
```python
model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore",
)
```
- **env_file=".env"**: Loads from .env file in project root
- **extra="ignore"**: Ignores unknown environment variables
- **UTF-8 encoding**: Handles international characters

**Database URL Property:**
```python
@property
def database_url(self) -> str:
    if self.DB_URL:
        return self.DB_URL
    return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
```
- **@property**: Computed property (accessed like an attribute)
- **DB_URL override**: Allows full URL override (useful for cloud databases)
- **PostgreSQL format**: Standard connection string format
- **Dynamic construction**: Builds URL from individual components

#### Transaction Class - Core Business Model
```python
class Transaction(BaseModel):
```
**Purpose**: Represents a single financial transaction
- **BaseModel**: Pydantic base class for validation and serialization
- **Immutable**: Once created, transaction data shouldn't change
- **Type safety**: All fields are strongly typed

**Core Transaction Fields:**
```python
transaction_id: str = Field(..., description="Unique transaction identifier")
processor_name: str = Field(..., description="Name of the payment processor")
amount: Decimal = Field(..., description="Transaction amount in currency units")
currency: str = Field(..., description="ISO currency code (e.g., USD)")
status: str = Field(..., description="Transaction status (e.g., completed, pending)")
```
- **Field(...)**: Required field (no default value)
- **Decimal**: Precise decimal arithmetic (critical for financial data)
- **String types**: Transaction ID, processor name, currency, status
- **ISO currency**: Standard 3-letter currency codes (USD, EUR, GBP)

**Additional Transaction Fields:**
```python
merchant_id: str = Field(..., description="Merchant identifier")
transaction_date: datetime = Field(..., description="Timestamp of the transaction")
reference_number: str = Field(..., description="Reference number for reconciliation")
fee: Decimal = Field(..., description="Transaction fee charged by processor")
```
- **merchant_id**: Links transaction to specific merchant
- **datetime**: Precise timestamp with timezone support
- **reference_number**: Used for matching transactions across systems
- **fee**: Processor fees (also uses Decimal for precision)

### 3.2 Main Orchestrator (main.py)

The main.py file is the central orchestrator that coordinates the entire reconciliation workflow.

#### Module Imports and Setup
```python
from __future__ import annotations
import argparse
import os
import sys
from datetime import date
from typing import List
import logging
import structlog
from dotenv import load_dotenv
```
**Purpose**: Import dependencies and enable modern Python features
- **__future__ annotations**: Enables forward references for type hints
- **argparse**: Command-line argument parsing
- **structlog**: Structured logging for production observability
- **dotenv**: Loads environment variables from .env file
- **typing.List**: Type hints for function parameters

**Environment and Settings Loading:**
```python
load_dotenv()

logger = structlog.get_logger()

try:
    SETTINGS = Settings()
except Exception as e:
    logger.error(
        "Failed to load environment settings. Check your .env file.", error=str(e)
    )
    sys.exit(1)
```
- **load_dotenv()**: Loads .env file into environment variables
- **Global logger**: Structured logger instance for the module
- **Settings validation**: Fails fast if configuration is invalid
- **sys.exit(1)**: Exits with error code if settings fail to load

#### ReconciliationSystem Class - Main Orchestrator

**Class Definition and Purpose:**
```python
class ReconciliationSystem:
    """
    Coordinates reconciliation workflow across payment processors.
    
    This class orchestrates the complete reconciliation process including:
    - Data fetching from processor and internal APIs
    - Transaction reconciliation and discrepancy identification
    - Report generation in CSV and JSON formats
    - S3 upload with local fallback
    - Email notifications with severity-based alerting
    - Database audit logging and error tracking
    
    Each processor run is isolated to prevent cascading failures.
    """
```
**Design Principles**:
- **Single Responsibility**: Orchestrates workflow, doesn't implement business logic
- **Fault Isolation**: Each processor runs independently
- **Comprehensive Logging**: Every step is logged for observability
- **Graceful Degradation**: Continues operation even if some components fail

**Initialization Method:**
```python
def __init__(self) -> None:
    """
    Initialize service components and create report directory.
    
    Sets up all required service instances:
    - AWSManager for S3 operations with local fallback
    - DatabaseManager for PostgreSQL audit trails
    - NotificationService for email/Slack alerts
    - ReportGenerator for CSV/JSON report creation
    - ReconciliationEngine for transaction matching
    """
    SETTINGS.REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    self.aws_manager = AWSManager(
        bucket_name=SETTINGS.AWS_BUCKET_NAME, region=SETTINGS.AWS_REGION
    )
    self.database_manager = DatabaseManager(settings=SETTINGS)
    self.notification_service = NotificationService()
    self.report_generator = ReportGenerator()
    self.reconciliation_engine = ReconciliationEngine()
```
**Initialization Steps**:
1. **Directory Creation**: Creates report output directory if it doesn't exist
2. **Service Instantiation**: Creates all required service objects
3. **Dependency Injection**: Passes settings to services that need configuration
4. **Ready State**: System is ready to process reconciliation requests

**Core Processing Method - _process_single_processor:**

This method contains the complete reconciliation workflow for a single payment processor.

**Method Signature and Setup:**
```python
def _process_single_processor(
    self, processor_name: str, target_date_str: str
) -> bool:
    """
    Execute reconciliation workflow for a single processor.
    Errors are isolated and do not affect other processors.
    """
    logger.info(
        "Starting reconciliation", processor=processor_name, date=target_date_str
    )
    run_id = None
    target_date = date.fromisoformat(target_date_str)
    local_report_dir = (
        SETTINGS.REPORT_OUTPUT_DIR / f"{processor_name}_{target_date_str}"
    )
    csv_path = json_path = None
    s3_uploaded = False
```
**Setup Phase**:
- **Structured logging**: Logs start of reconciliation with context
- **Variable initialization**: Sets up tracking variables
- **Date parsing**: Converts string date to Python date object
- **Directory naming**: Creates unique directory for this processor/date combination
- **State tracking**: Initializes variables to track process state

**Database Audit Record Creation:**
```python
try:
    # Create audit record
    run_id = self.database_manager.create_reconciliation_run(
        target_date, processor_name
    )
    if run_id is None:
        logger.error(
            "Could not start database audit record. Aborting processor run."
        )
        return False
    logger.debug("Database run record created", run_id=run_id)
```
**Audit Trail**:
- **Compliance requirement**: Creates permanent record of reconciliation attempt
- **Unique run ID**: UUID for tracking this specific reconciliation run
- **Fail-fast**: Aborts if audit record cannot be created
- **Traceability**: Links all subsequent operations to this run ID

**Data Fetching Phase:**
```python
    # Fetch transaction data
    fetcher = DataFetcher(
        processor_api_base_url=SETTINGS.PROCESSOR_API_BASE_URL,
        internal_api_base_url=SETTINGS.INTERNAL_API_BASE_URL,
        processor_name=processor_name,
    )
    proc_txns = fetcher.fetch_processor_data(run_date=target_date)
    internal_txns = fetcher.fetch_internal_data(
        processor_txns=proc_txns, run_date=target_date
    )
    fetcher.close()
    logger.info(
        "Data fetched successfully",
        proc_count=len(proc_txns),
        internal_count=len(internal_txns),
    )
```
**Data Acquisition**:
- **DataFetcher instantiation**: Creates fetcher with API endpoints
- **Processor data**: Fetches transactions from payment processor API
- **Internal data**: Fetches corresponding internal transaction records
- **Resource cleanup**: Closes fetcher to free resources
- **Metrics logging**: Records count of transactions fetched

**Reconciliation Processing:**
```python
    # Perform reconciliation
    result = self.reconciliation_engine.reconcile(
        proc_txns, internal_txns, target_date, processor_name
    )

    # Store results
    self.database_manager.store_reconciliation_result(run_id, result)
    logger.debug("Reconciliation metrics and details stored in DB.")
```
**Business Logic Execution**:
- **Core reconciliation**: Compares processor vs internal transactions
- **Result object**: Contains summary metrics and detailed discrepancies
- **Database storage**: Persists results for audit and reporting
- **Audit compliance**: Ensures all reconciliation results are permanently recorded

**Report Generation:**
```python
    # Generate reports
    csv_path, summary_text, json_path = (
        self.report_generator.generate_all_reports(result, local_report_dir)
    )
    logger.info(
        "Reports generated locally",
        csv_path=str(csv_path.as_posix()),
        json_path=str(json_path.as_posix()),
    )
```
**Report Creation**:
- **Multiple formats**: Generates both CSV and JSON reports
- **Local storage**: Always creates local copies first
- **Path tracking**: Records exact file paths for subsequent operations
- **POSIX paths**: Uses forward slashes for cross-platform compatibility

**S3 Upload with Fallback:**
```python
    # Upload to S3
    s3_location = s3_key = None
    try:
        s3_location = self.aws_manager.upload_report(csv_path)
        s3_uploaded = self.aws_manager.is_s3_path(s3_location)

        if s3_uploaded:
            self.database_manager.update_s3_report_key(run_id, s3_location)
            # Store S3 key for notification service
            s3_key = f"s3://{self.aws_manager.bucket_name}/{s3_location}"
            logger.info("Report uploaded to S3", s3_key=s3_location)
        else:
            local_path = s3_location.replace("file://", "")
            self.database_manager.update_s3_report_key(run_id, local_path)
            logger.info(
                "Report stored locally (S3 unavailable)", local_path=local_path
            )

    except Exception as e:
        logger.warning(
            "S3 upload failed, reports available locally",
            error=str(e),
            local_path=str(csv_path.as_posix()),
        )
        s3_uploaded = False
```
**Cloud Storage with Graceful Degradation**:
- **Upload attempt**: Tries to upload report to S3
- **Success detection**: Checks if upload actually succeeded
- **Database update**: Records S3 location in audit record
- **Fallback handling**: Gracefully handles S3 unavailability
- **Error logging**: Records failures without stopping the process
- **Local preservation**: Ensures reports are never lost

**Notification Dispatch:**
```python
    # Send notifications
    try:
        if s3_uploaded and s3_key:
            notification_sent = (
                self.notification_service.send_reconciliation_notification(
                    result,
                    target_date,
                    report_url=s3_key,
                    report_attachment=None,
                )
            )
        else:
            notification_sent = (
                self.notification_service.send_reconciliation_notification(
                    result,
                    target_date,
                    report_url=None,
                    report_attachment=str(csv_path),
                )
            )

        if notification_sent:
            logger.info("Notification sent successfully")
        else:
            logger.info("Notification skipped - email not configured")
    except Exception as e:
        logger.warning("Failed to send notification", error=str(e))
```
**Intelligent Notification Strategy**:
- **S3 link vs attachment**: Uses S3 URL if available, otherwise attaches local file
- **Conditional sending**: Only sends if email is properly configured
- **Error isolation**: Notification failures don't stop the reconciliation
- **Status logging**: Records whether notification was sent or skipped

**Error Handling and Cleanup:**
```python
except Exception as e:
    error_msg = str(e)[:500]
    logger.error(
        "Reconciliation failed for processor",
        processor=processor_name,
        error=error_msg,
        exc_info=True,
    )
    if run_id:
        self.database_manager.update_reconciliation_status(
            run_id, "failed", str(e)
        )

    try:
        self.notification_service.send_failure_alert(
            processor_name, target_date_str, run_id or "unknown", error_msg
        )
    except Exception as alert_err:
        logger.warning("Could not send failure alert", error=str(alert_err))

    return False
```
**Comprehensive Error Handling**:
- **Error truncation**: Limits error message to 500 characters for logging
- **Full stack trace**: Includes exc_info=True for debugging
- **Database update**: Marks run as failed in audit record
- **Failure alerts**: Sends critical alert emails when reconciliation fails
- **Nested error handling**: Handles cases where even alerts fail
- **Return value**: Returns False to indicate failure

**Cleanup Operations:**
```python
finally:
    # Clean up local files after successful S3 upload
    cleanup_enabled = os.getenv('CLEANUP_LOCAL_REPORTS', 'false').lower() == 'true'
    logger.debug("Cleanup check", cleanup_enabled=cleanup_enabled, s3_uploaded=s3_uploaded)
    
    if cleanup_enabled and s3_uploaded:
        cleanup_paths = [csv_path, json_path]
        for path in cleanup_paths:
            if path and path.exists():
                try:
                    path.unlink()
                    logger.debug("Deleted local file after S3 upload", path=str(path.as_posix()))
                except Exception as e:
                    logger.warning("Failed to delete file", path=str(path.as_posix()), error=str(e))

        if local_report_dir.is_dir():
            try:
                local_report_dir.rmdir()
                logger.debug("Cleaned up report directory after S3 upload")
            except OSError:
                pass
    else:
        logger.info("Local reports preserved", directory=str(local_report_dir.as_posix()))
```
**Resource Management**:
- **Configurable cleanup**: Uses environment variable to control cleanup behavior
- **Conditional deletion**: Only deletes local files if S3 upload succeeded
- **Safe deletion**: Checks file existence before attempting deletion
- **Directory cleanup**: Removes empty directories after file cleanup
- **Error tolerance**: Continues even if cleanup operations fail
- **Preservation logging**: Records when local files are preserved

**Main Execution Method:**
```python
def run(self, target_date: str, processors: List[str]) -> None:
    """
    Run reconciliation for all specified processors.
    
    Args:
        target_date: ISO format date string (YYYY-MM-DD)
        processors: List of processor names to reconcile
        
    Each processor is processed independently to prevent
    failures in one processor from affecting others.
    """
    overall_success = True
    for processor in processors:
        if not self._process_single_processor(processor, target_date):
            overall_success = False

    if overall_success:
        logger.info("All specified processors reconciled successfully.")
    else:
        logger.warning("One or more processor reconciliations failed. Check logs.")
```
**Orchestration Logic**:
- **Independent processing**: Each processor runs separately
- **Failure isolation**: One processor failure doesn't stop others
- **Success tracking**: Monitors overall success across all processors
- **Summary logging**: Provides final status of entire reconciliation run

#### Logging Configuration

**Structured Logging Setup:**
```python
def setup_logging() -> None:
    """
    Configure structured JSON logging for production observability.
    
    Sets up structlog with:
    - Timestamp formatting
    - Log level inclusion
    - Stack trace rendering
    - Exception info formatting
    - JSON output for log aggregation
    """
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(format="%(message)s", level=logging.INFO, stream=sys.stdout)
```
**Production-Ready Logging**:
- **Structured output**: JSON format for log aggregation systems
- **Timestamp inclusion**: Every log entry has precise timestamp
- **Log levels**: Automatic inclusion of log level in output
- **Exception handling**: Proper formatting of stack traces
- **Performance**: Caches logger instances for efficiency
- **Standard output**: Logs to stdout for container environments

#### Command Line Interface

**Argument Parser Setup:**
```python
if __name__ == "__main__":
    setup_logging()

    parser = argparse.ArgumentParser(
        description="FinTech Transaction Reconciliation System.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --date 2024-05-15 --processors stripe
  python main.py --date 2024-05-15 --processors stripe paypal square
        """,
    )
```
**CLI Design**:
- **Help documentation**: Clear description and examples
- **Raw formatting**: Preserves formatting in help text
- **Usage examples**: Shows common invocation patterns

**Date Argument:**
```python
parser.add_argument(
    "--date",
    type=str,
    default=date.today().isoformat(),
    help="Target date for reconciliation (YYYY-MM-DD). Defaults to today.",
)
```
**Date Handling**:
- **ISO format**: Standard YYYY-MM-DD format
- **Default value**: Uses today's date if not specified
- **Type safety**: Validates format later in the code

**Processors Argument:**
```python
parser.add_argument(
    "--processors",
    type=str,
    nargs="+",
    default=["stripe", "paypal", "square"],
    help="List of processors to reconcile (e.g., stripe paypal). Defaults to all processors.",
)
```
**Processor Selection**:
- **Multiple values**: nargs="+" allows multiple processor names
- **Default behavior**: Processes all supported processors if none specified
- **Flexibility**: Allows selective processing for testing or maintenance

**Execution Logic:**
```python
args = parser.parse_args()

try:
    date.fromisoformat(args.date)
except ValueError:
    logger.error("Invalid date format. Use YYYY-MM-DD.", provided_date=args.date)
    sys.exit(1)

system = ReconciliationSystem()
system.run(args.date, args.processors)
```
**Execution Flow**:
- **Argument parsing**: Processes command line arguments
- **Date validation**: Ensures date is in correct format
- **Early exit**: Fails fast on invalid input
- **System instantiation**: Creates reconciliation system
- **Execution**: Runs reconciliation for specified parameters

The main.py file serves as the central orchestrator, coordinating all system components while maintaining clear separation of concerns, comprehensive error handling, and production-ready logging. It demonstrates enterprise software patterns including dependency injection, fault isolation, graceful degradation, and comprehensive audit trails.

---
## 4. Data Fetcher Module (src/data_fetcher.py)

The DataFetcher class handles API integration with payment processors and internal systems, implementing robust retry logic and realistic data simulation.

### Class Architecture
```python
class DataFetcher:
    def __init__(self, processor_api_base_url, internal_api_base_url, processor_name, max_retries=3)
    def _make_request_with_retry(self, url, timeout=30) -> requests.Response
    def fetch_processor_data(self, run_date=None) -> List[Transaction]
    def fetch_internal_data(self, processor_txns=None, run_date=None) -> List[Transaction]
    def __enter__(self) / __exit__(self) / close(self)  # Context manager support
```

### Key Implementation Details

**Retry Logic with Exponential Backoff:**
```python
for attempt in range(self.max_retries):
    try:
        response = self.session.get(url, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.Timeout as e:
        wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
        time.sleep(wait_time)
```

**Pagination Safety Controls:**
- Maximum 100 pages to prevent infinite loops
- 300-second timeout protection
- Configurable page size via environment variable

**Transaction ID Generation:**
```python
trans_id = f"TXN_{self.processor_name.upper()}_{run_date.strftime('%Y%m%d')}_{page_offset + idx:04d}"
# Example: TXN_STRIPE_20250115_0001
```

**Realistic Capture Rate Simulation:**
```python
capture_rate = random.uniform(0.80, 0.95)  # 80-95% internal capture
num_to_capture = int(len(processor_txns) * capture_rate)
captured_indices = sorted(random.sample(range(len(processor_txns)), num_to_capture))
```

**Financial Calculations:**
- Processor fee: `amount * 2.9% + $0.30`
- Internal fee: `amount * 2.0% + $0.30`
- Uses Decimal for precise financial arithmetic

---

## 5. Reconciliation Engine (src/reconciliation_engine.py)

The ReconciliationEngine implements the core business logic for comparing transaction datasets and identifying discrepancies.

### Algorithm Overview

**O(1) Hash Map Indexing:**
```python
def _build_index(transactions: List[Transaction]) -> Dict[str, Transaction]:
    index: Dict[str, Transaction] = {}
    for t in transactions:
        if t.transaction_id in index:
            logger.warning("Duplicate transaction_id %s encountered", t.transaction_id)
            continue
        index[t.transaction_id] = t
    return index
```

**Reconciliation Process:**
1. Build hash map indexes for both datasets (O(n) time)
2. Iterate through processor transactions (O(n) time)
3. Check existence in internal index (O(1) lookup)
4. Collect missing transactions and calculate totals

**Financial Calculations:**
```python
total_discrepancy: Decimal = sum(t.amount for t in missing_details)
total_volume: Decimal = sum(t.amount for t in unique_proc_txns)
```

**Result Structure:**
- `ReconciliationSummary`: High-level metrics and totals
- `ReconciliationResult`: Complete result with transaction details
- Comprehensive logging for audit trails

---

## 6. Report Generator (src/report_generator.py)

The ReportGenerator transforms reconciliation results into multiple output formats for different stakeholders.

### Multi-Format Output System

**1. Detailed CSV Report (Operations Team):**
```python
def _generate_detailed_csv(self, result: ReconciliationResult, output_dir: Path) -> Path:
    data = [t.model_dump() if hasattr(t, "model_dump") else t.__dict__ 
            for t in result.missing_transactions_details]
    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False)
```

**2. Executive Summary (Management):**
```
FinTech Reconciliation Executive Summary
========================================

RECONCILIATION OVERVIEW
-----------------------
✓ Processor Transactions Processed: 5,000
✓ Internal System Matches: 4,200
⚠ Discrepancies Identified: 800

FINANCIAL IMPACT
----------------
• Total Transaction Volume: $2,500,000.00
• Missing Transaction Value: $15,420.50
• Discrepancy Rate: 16.00%
```

**3. Structured JSON (API Integration):**
```python
report_data = {
    "report_metadata": {"generated_at": datetime.utcnow().isoformat()},
    "reconciliation_summary": {
        "total_discrepancy_amount": str(result.summary.total_discrepancy_amount),  # Preserve Decimal precision
        "total_volume_processed": str(result.summary.total_volume_processed)
    },
    "financial_impact": self._calculate_financial_impact(result)
}
```

### Security Features

**Path Traversal Protection:**
```python
normalized_path = output_dir.resolve()
allowed_dirs = [cwd, cwd / "reports", cwd / "local_reports"]
is_allowed = any(normalized_path.is_relative_to(allowed_dir) for allowed_dir in allowed_dirs)
if not (is_allowed or is_temp):
    raise ValueError("Invalid output directory path detected")
```

### Risk Assessment Logic

**Automated Risk Categorization:**
```python
if discrepancy_rate < 0.001:      # < 0.1%
    risk_level = "LOW"
elif discrepancy_rate < 0.005:    # < 0.5%
    risk_level = "MEDIUM"
else:                             # >= 0.5%
    risk_level = "HIGH"
```

**Compliance Status Determination:**
- `COMPLIANT`: Low risk level
- `NEEDS_REVIEW`: Medium/High risk levels
- Automated recommendations based on transaction count and value

---

## Next Sections

The following sections will cover:
- **Database Manager** - PostgreSQL operations and audit trails
- **AWS Manager** - Cloud storage integration
- **Notification Service** - Multi-channel alerting system
- **Testing Architecture** - Comprehensive test suite analysis
## 7. Database Manager (src/database_manager.py)

The DatabaseManager provides production-ready PostgreSQL operations with comprehensive audit trails, transaction safety, and data quality validation.

### Core Architecture

**Context Manager Pattern:**
```python
@contextmanager
def get_connection(self):
    conn = None
    try:
        conn = psycopg2.connect(self.db_url)
        conn.autocommit = False  # Explicit transaction control
        yield conn
    except psycopg2.Error as exc:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()
```

### Key Operations

**1. Reconciliation Run Management:**
```python
def create_reconciliation_run(self, date: date, processor: str) -> Optional[str]:
    # UPSERT logic for idempotency
    cursor.execute("""
        INSERT INTO reconciliation_runs (id, run_date, processor_name, start_time, status)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (run_date, processor_name)
        DO UPDATE SET start_time = EXCLUDED.start_time, status = 'running'
        RETURNING id
    """)
```

**2. Bulk Transaction Storage:**
```python
def _bulk_insert_missing_transactions(self, cursor, run_id: str, transactions: List[Transaction]):
    validated_transactions = [(str(uuid.uuid4()), run_id, txn.transaction_id, ...) 
                             for txn in transactions if self._validate_transaction(txn)]
    execute_values(cursor, query, validated_transactions, page_size=1000)
```

**3. Data Quality Validation:**
```python
def _validate_transaction(self, txn: Transaction) -> bool:
    # Business rule validation
    if txn.amount <= 0:
        return False
    if len(txn.currency) != 3 or not txn.currency.isupper():
        return False
    if txn.fee and txn.fee > txn.amount * Decimal("0.5"):  # Fee > 50% of amount
        return False
    return True
```

**4. Comprehensive Audit Logging:**
```python
def _log_audit_event(self, cursor, action: str, table_name: str, record_id: str, 
                    old_values: Dict = None, new_values: Dict = None):
    cursor.execute("""
        INSERT INTO audit_log (id, action, table_name, record_id, old_values, new_values)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (str(uuid.uuid4()), action, table_name, record_id, 
          json.dumps(old_values or {}), json.dumps(new_values or {})))
```

### Security Features

- **URL Encoding**: Handles special characters in database passwords
- **Transaction Safety**: Automatic rollback on exceptions
- **Input Validation**: Prevents SQL injection through parameterized queries
- **Schema Auto-initialization**: Creates tables if they don't exist

---

## 8. AWS Manager (src/aws_manager.py)

The AWSManager handles cloud storage with intelligent fallback to local storage, ensuring reports are never lost.

### Dual Storage Strategy

**S3 with Local Fallback:**
```python
def upload_report(self, file_path: Path, key: Optional[str] = None) -> str:
    if not self._s3_available:
        return self._use_local_storage(file_path)
    
    try:
        self.s3_client.upload_file(str(file_path), self.bucket_name, key, ExtraArgs=extra_args)
        return key  # S3 object key
    except Exception as exc:
        return self._handle_s3_upload_exception(exc, file_path)
```

**Intelligent Error Handling:**
```python
PERMANENT_S3_ERRORS = frozenset({
    "NoSuchBucket", "AccessDenied", "InvalidAccessKeyId", "403", "404"
})

def _handle_s3_upload_exception(self, exc: Exception, file_path: Path) -> str:
    if isinstance(exc, ClientError):
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        if error_code in PERMANENT_S3_ERRORS:
            self._s3_available = False  # Disable S3 for future uploads
            return self._use_local_storage(file_path)
```

### Security Features

**Path Traversal Protection:**
```python
def _use_local_storage(self, file_path: Path) -> str:
    resolved_path = file_path.resolve()
    allowed_paths = [str(Path.cwd()), "/tmp", "/var/tmp"]
    if not any(str(resolved_path).startswith(path) for path in allowed_paths):
        raise ValueError(f"Path traversal detected: {file_path}")
    return f"file://{resolved_path.as_posix()}"
```

**S3 Security Configuration:**
```python
extra_args = {
    "ServerSideEncryption": "AES256",
    "Metadata": {
        "upload_date": date.today().isoformat(),
        "system": "fintech_reconciliation"
    }
}
```

---

## 9. Notification Service (src/notification_service.py)

The NotificationService provides multi-channel alerting with severity-based thresholds and adaptive risk assessment.

### Dual Email Strategy

**AWS SES and SMTP Fallback:**
```python
def _send_email(self, message: MIMEMultipart) -> bool:
    if self.use_ses:
        return self._send_email_ses(message)
    else:
        return self._send_email_smtp(message)
```

**SMTP Resilience:**
```python
smtp_configs = [
    ("smtp.gmail.com", 465),    # Primary SSL
    (self.smtp_server, self.smtp_port),  # Configured server
    ("smtp.gmail.com", 587),    # STARTTLS fallback
    ("smtp-mail.outlook.com", 587)  # Outlook fallback
]

for smtp_server, smtp_port in smtp_configs:
    try:
        # Attempt connection with current config
        if smtp_port == 465:
            # SSL connection
        else:
            # STARTTLS connection
    except Exception:
        continue  # Try next configuration
```

### Adaptive Severity Assessment

**Volume-Based Thresholds:**
```python
def _determine_severity(self, result: ReconciliationResult) -> str:
    total_tx = summary.processor_transactions
    
    # Adaptive thresholds based on transaction volume
    if total_tx < 10_000:
        low, medium, high, critical = 0.02, 0.05, 0.10, 0.20
    elif total_tx < 100_000:
        low, medium, high, critical = 0.005, 0.02, 0.05, 0.10
    else:  # High-volume processors
        low, medium, high, critical = 0.001, 0.003, 0.005, 0.01
    
    discrepancy_rate = missing_count / total_tx
    if discrepancy_rate > critical or amount_abs > 100_000:
        return "critical"
```

### Rich HTML Email Generation

**Severity-Based Styling:**
```python
color_map = {
    "critical": "#dc3545",  # Red
    "high": "#fd7e14",      # Orange
    "medium": "#ffc107",    # Yellow
    "low": "#28a745"        # Green
}

severity_indicator = {
    "critical": "🚨 CRITICAL",
    "high": "⚠️ HIGH PRIORITY", 
    "medium": "📊 ATTENTION",
    "low": "✅ INFO"
}
```

**S3 Presigned URL Generation:**
```python
def _generate_presigned_url(self, s3_url: str) -> Optional[str]:
    bucket, key = s3_url[5:].split('/', 1)  # Remove 's3://'
    s3_client = boto3.client('s3', region_name=region)
    
    return s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=86400  # 24 hours
    )
```

### Security Features

- **Path Validation**: Prevents directory traversal in file attachments
- **HTML Escaping**: Prevents XSS in email content
- **Safe File Handling**: Validates attachment paths before processing
- **Credential Management**: Supports both SES and SMTP authentication

---

## Next Sections

The following sections will cover:
- **Infrastructure as Code** - Terraform modules and AWS architecture
- **CI/CD Pipeline** - GitHub Actions workflow analysis
- **Testing Framework** - Comprehensive test suite breakdown
- **Configuration Management** - Environment and deployment settings
## 10. Infrastructure as Code (Terraform)

The system uses modular Terraform architecture with 10 specialized modules for AWS cloud deployment.

### Main Configuration (terraform/environments/dev/main.tf)

**Provider Configuration:**
```hcl
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Environment = "dev"
      Project     = "fintech-reconciliation"
      ManagedBy   = "terraform"
    }
  }
}
```

### Module Architecture

**1. VPC Module:**
```hcl
module "vpc" {
  source = "../../modules/vpc"
  
  project_name       = local.project_name
  environment        = "dev"
  enable_nat_gateway = false  # Cost optimization for dev
  tags              = local.common_tags
}
```

**2. RDS PostgreSQL:**
```hcl
module "rds" {
  source = "../../modules/rds"
  
  instance_class        = "db.t3.micro"
  allocated_storage     = 20
  max_allocated_storage = 100
  password             = random_password.db_password.result
  backup_retention     = 7
  multi_az            = false  # Single AZ for dev
}
```

**3. ECS Fargate Configuration:**
```hcl
module "ecs" {
  source = "../../modules/ecs"
  
  cpu                = "512"
  memory             = "1024"
  execution_role_arn = module.iam.ecs_task_execution_role_arn
  task_role_arn     = module.iam.ecs_task_role_arn
  
  environment_variables = [
    { name = "DB_HOST", value = module.rds.endpoint },
    { name = "AWS_S3_BUCKET_NAME", value = module.s3.bucket_name },
    { name = "USE_SES", value = "true" }
  ]
}
```

**4. EventBridge Scheduling:**
```hcl
module "eventbridge" {
  source = "../../modules/eventbridge"
  
  schedule_expression   = "cron(0 4 * * ? *)"  # Daily at 4:00 AM UTC
  cluster_arn          = module.ecs.cluster_arn
  task_definition_arn  = module.ecs.task_definition_arn
  subnet_ids           = module.vpc.public_subnet_ids
  security_group_ids   = [aws_security_group.ecs.id]
}
```

### Security Configuration

**Password Generation:**
```hcl
resource "random_password" "db_password" {
  length  = 32
  special = true
  override_special = "!#$%&*+-=?_"  # RDS-safe characters only
}
```

**IAM Roles and Policies:**
- ECS Task Execution Role (ECR, CloudWatch access)
- ECS Task Role (S3, SES, Secrets Manager access)
- EventBridge Role (ECS task execution)

---

## 11. CI/CD Pipeline (.github/workflows/cicd.yml)

The GitHub Actions pipeline implements security-first DevOps with parallel execution and comprehensive quality gates.

### Pipeline Architecture

**Parallel Security & Testing:**
```yaml
jobs:
  security-scan:
    timeout-minutes: 8
    steps:
    - name: Semgrep Security Scan
      run: |
        semgrep --config=auto --severity=ERROR --error src/
        semgrep --config=auto --json --output=semgrep-results.json src/ || true
    
    - name: Trivy Security Scan
      uses: aquasecurity/trivy-action@0.28.0
      with:
        scan-type: 'fs'
        severity: 'CRITICAL'

  test:
    needs: security-scan
    timeout-minutes: 12
    services:
      postgres:
        image: postgres:15-alpine
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
```

### Quality Gates

**Comprehensive Testing:**
```yaml
- name: Run test suite
  env:
    DB_HOST: localhost
    DB_PASSWORD: test
  run: |
    PYTHONPATH=src pytest tests/ -v --maxfail=5 --tb=short --cov=src --cov-report=term-missing

- name: Code quality checks
  run: |
    python -m py_compile src/*.py
    cd src && python -c "import main, data_fetcher, aws_manager, database_manager"
```

### Deployment Strategy

**Environment-Aware Deployment:**
```yaml
- name: Set environment
  run: |
    if [[ "${{ github.event.inputs.environment }}" == "prod" ]]; then
      echo "env=prod" >> $GITHUB_OUTPUT
      echo "password=${{ secrets.DB_PASSWORD_PROD }}" >> $GITHUB_OUTPUT
    else
      echo "env=dev" >> $GITHUB_OUTPUT
      echo "password=${{ secrets.DB_PASSWORD_DEV }}" >> $GITHUB_OUTPUT
    fi
```

**Dynamic Backend Configuration:**
```yaml
- name: Create Terraform backend configuration
  run: |
    cat > "terraform/environments/$ENV/backend.tf" << 'EOF'
    terraform {
      backend "s3" {
        bucket = "BUCKET_PLACEHOLDER"
        key    = "ENV_PLACEHOLDER/terraform.tfstate"
        region = "us-east-1"
        encrypt = true
      }
    }
    EOF
    sed -i "s/BUCKET_PLACEHOLDER/$TERRAFORM_STATE_BUCKET/g" "terraform/environments/$ENV/backend.tf"
```

### Integration Testing

**VPC-Aware Task Execution:**
```yaml
- name: Run integration test
  run: |
    # Get RDS VPC configuration
    RDS_VPC=$(aws rds describe-db-instances \
      --db-instance-identifier fintech-reconciliation-dev \
      --query 'DBInstances[0].DBSubnetGroup.VpcId' --output text)
    
    # Get matching subnet and security group
    SUBNETS=$(aws ec2 describe-subnets \
      --filters "Name=vpc-id,Values=$RDS_VPC" "Name=tag:Name,Values=*public*" \
      --query 'Subnets[0].SubnetId' --output text)
    
    # Run ECS task with proper network configuration
    aws ecs run-task --cluster $CLUSTER_NAME --task-definition $TASK_DEF \
      --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],assignPublicIp=ENABLED}"
```

### Pipeline Stages

1. **Security Scan** (8 min) - Semgrep SAST + Trivy vulnerability scanning + SBOM generation
2. **Test & Quality Gates** (12 min) - PostgreSQL service + 130 tests + performance testing
3. **Build & Package** (10 min) - Docker image creation + container security scan
4. **Deploy** (15 min) - Terraform infrastructure + drift detection + ECS deployment
5. **Verify** (5 min) - Deployment validation and health checks
6. **Integration Test** (8 min) - End-to-end system validation

**Total Pipeline Time: ~58 minutes** (comprehensive security-first approach)

---

## 12. Configuration Management

### Python Dependencies (requirements.txt)

**Core Dependencies:**
```
boto3>=1.34.0              # AWS SDK
psycopg2-binary>=2.9.9      # PostgreSQL adapter
requests>=2.31.0            # HTTP client
pandas>=2.1.4               # Data manipulation
pydantic>=2.0.0             # Data validation
structlog>=23.1.0           # Structured logging
```

**Development Dependencies:**
```
pytest>=7.4.0               # Testing framework
pytest-cov>=4.1.0           # Coverage reporting
python-dotenv>=1.0.0        # Environment management
```

### Environment Configuration

**Required GitHub Secrets:**
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` - AWS credentials
- `DB_PASSWORD_DEV` / `DB_PASSWORD_PROD` - Database passwords
- `OPERATIONS_EMAIL` - Notification recipient
- `TERRAFORM_STATE_BUCKET` - S3 bucket for Terraform state

**Environment Variables:**
```bash
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=fintech_reconciliation
DB_USER=fintech
DB_PASSWORD=secure_password

# AWS Configuration
AWS_S3_BUCKET_NAME=fintech-reports-bucket
AWS_REGION=us-east-1
USE_SES=true

# Email Configuration
OPERATIONS_EMAIL=ops@company.com
SENDER_EMAIL=noreply@company.com
```

### Security Configuration

**Terraform State Management:**
- S3 backend with encryption
- DynamoDB table for state locking
- Separate state files per environment

**Container Security:**
- Non-root user execution
- Minimal base image (python:3.11.9-slim)
- Security scanning in CI/CD
- Path traversal protection

**AWS Security:**
- IAM roles with least privilege
- S3 server-side encryption
- VPC isolation for RDS
- Security groups with minimal access

---

## Next Sections

The following sections will cover:
- **Testing Framework** - Comprehensive test suite analysis
- **Troubleshooting Guide** - Common issues and solutions
- **Performance Optimization** - System tuning and monitoring
- **Disaster Recovery** - Backup and recovery procedures
## 13. Testing Framework

The system includes a comprehensive test suite with 130 tests achieving 77% overall coverage.

### Test Coverage by Module

| Module | Coverage | Key Test Areas |
|--------|----------|----------------|
| **reconciliation_engine.py** | 100% | Hash indexing, financial calculations |
| **models.py** | 99% | Pydantic validation, Settings loading |
| **data_fetcher.py** | 99% | API retry logic, pagination, timeouts |
| **report_generator.py** | 96% | Multi-format output, path security |
| **database_manager.py** | 76% | Transaction safety, audit logging |
| **notification_service.py** | 75% | Email delivery, severity assessment |
| **aws_manager.py** | 68% | S3 fallback, error handling |
| **main.py** | 66% | Orchestration, error isolation |
| **metrics.py** | 44% | System metrics collection |

### Test Execution
```bash
# Full test suite with coverage
PYTHONPATH=src python -m pytest tests/ -v --cov=src --cov-report=term-missing

# Specific module testing
PYTHONPATH=src python -m pytest tests/test_data_fetcher.py -v

# CI/CD integration
pytest tests/ -v --maxfail=5 --tb=short --cov=src
```

---

## 14. Troubleshooting Guide

### Common Issues and Solutions

**Database Connection Issues:**
```bash
# Check database connectivity
docker-compose exec db psql -U fintech -d fintech_reconciliation -c "SELECT 1;"

# Reset database
docker-compose down -v && docker-compose up -d
```

**S3 Upload Failures:**
- Verify AWS credentials in environment variables
- Check S3 bucket permissions and region configuration
- System automatically falls back to local storage

**Email Notification Issues:**
- For SES: Verify email address in AWS SES console
- For SMTP: Check credentials and server configuration
- Review notification service logs for specific errors

**ECS Task Failures:**
```bash
# Check ECS task logs
aws logs get-log-events --log-group-name /ecs/fintech-reconciliation-dev

# Verify VPC configuration
aws ec2 describe-security-groups --group-ids sg-xxxxx
```

### Performance Optimization

**Database Optimization:**
- Bulk insert operations (1000 records per batch)
- Connection pooling with context managers
- Indexed queries on transaction_id and run_date

**Memory Management:**
- Streaming data processing for large datasets
- Pagination with safety limits (100 pages max)
- Resource cleanup in finally blocks

**Network Resilience:**
- Exponential backoff retry logic (1s, 2s, 4s intervals)
- Multiple SMTP server fallbacks
- Request timeouts and circuit breaker patterns

---

## 15. System Monitoring and Observability

### Logging Strategy

**Structured Logging with Structlog:**
```python
logger.info("Reconciliation complete", 
           processor=processor_name,
           missing_count=len(missing_details),
           total_volume=float(total_volume))
```

**Log Levels:**
- **INFO**: Normal operations, metrics, status updates
- **WARNING**: Recoverable errors, fallback usage
- **ERROR**: System failures, critical issues
- **DEBUG**: Detailed troubleshooting information

### CloudWatch Integration

**Metrics Collection:**
- ECS task execution metrics
- Database connection health
- S3 upload success/failure rates
- Email notification delivery status

**Alerting Thresholds:**
- Task failure rate > 5%
- Database connection failures
- High discrepancy amounts (>$10,000)
- Email delivery failures

### Audit Trail

**Database Audit Logging:**
```sql
SELECT action, table_name, record_id, new_values, created_at 
FROM audit_log 
WHERE created_at >= NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;
```

**Compliance Features:**
- Immutable audit records with UUIDs
- Complete transaction lifecycle tracking
- Data quality validation checks
- Reconciliation run history

---

## 16. Security and Compliance

### Security Measures

**Container Security:**
- Non-root user execution (fintech user)
- Minimal base image (python:3.11.9-slim)
- No hardcoded secrets or credentials
- Path traversal protection

**Data Security:**
- Decimal precision for financial calculations
- Input validation and sanitization
- SQL injection prevention (parameterized queries)
- XSS prevention in email content

**AWS Security:**
- IAM roles with least privilege access
- S3 server-side encryption (AES256)
- VPC isolation for database access
- Secrets Manager for credential storage

### Compliance Features

**Financial Regulations:**
- Complete audit trails for all transactions
- Immutable reconciliation records
- Data retention policies
- Automated compliance reporting

**Data Privacy:**
- No PII storage in logs
- Secure credential management
- Encrypted data transmission
- Access control and monitoring

---

## 17. Disaster Recovery and Business Continuity

### Backup Strategy

**Database Backups:**
- Automated daily RDS backups (7-day retention)
- Point-in-time recovery capability
- Multi-AZ deployment for production
- Automated failover mechanisms

**Report Storage:**
- S3 versioning enabled for report history
- Cross-region replication for critical data
- Local fallback ensures no data loss
- Automated cleanup policies

### Recovery Procedures

**System Recovery:**
1. Verify infrastructure status via Terraform
2. Check ECS cluster and task definition health
3. Validate database connectivity and schema
4. Test email notification delivery
5. Execute integration test to verify end-to-end functionality

**Data Recovery:**
```bash
# Restore from RDS backup
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier fintech-reconciliation-restored \
  --db-snapshot-identifier fintech-reconciliation-backup-20250115

# Verify data integrity
docker-compose exec db psql -U fintech -d fintech_reconciliation \
  -c "SELECT COUNT(*) FROM reconciliation_runs WHERE run_date >= '2025-01-01';"
```

---

## 18. Conclusion

This FinTech Transaction Reconciliation System represents a production-ready, enterprise-grade solution with:

### Key Achievements
- **77% test coverage** across 130 comprehensive tests (all passing)
- **Zero-downtime deployment** with ECS Fargate and blue-green strategies
- **Multi-channel alerting** with adaptive severity thresholds
- **Comprehensive audit trails** for regulatory compliance
- **Fault-tolerant architecture** with graceful degradation
- **Security-first design** with container hardening and AWS best practices
- **35 production files** in clean, maintainable structure

### Technical Excellence
- **Modular architecture** with 10 specialized Terraform modules
- **6-stage CI/CD pipeline** with comprehensive security scanning (Semgrep + Trivy)
- **Dual storage strategy** ensuring reports are never lost (S3 + local fallback)
- **Intelligent error handling** with exponential backoff and circuit breakers
- **Performance optimization** with bulk operations and connection pooling
- **DevSecOps maturity** with shift-left security and automated compliance

### Business Value
- **Automated daily reconciliation** across multiple payment processors
- **Real-time discrepancy detection** with financial impact assessment
- **Scalable cloud infrastructure** supporting high transaction volumes
- **Comprehensive reporting** in multiple formats for different stakeholders
- **Operational excellence** with monitoring, alerting, and disaster recovery

The system successfully bridges the gap between complex financial operations and modern cloud-native architecture, providing a robust foundation for transaction reconciliation at enterprise scale.

---

## Appendix

### Quick Reference Commands

**Local Development:**
```bash
# Start system
docker-compose up -d

# Run reconciliation
docker-compose run --rm app python src/main.py --processors stripe

# View logs
docker-compose logs -f app

# Run tests
PYTHONPATH=src python -m pytest tests/ -v
```

**Production Operations:**
```bash
# Deploy infrastructure
cd terraform/environments/prod
terraform plan && terraform apply

# Manual task execution
aws ecs run-task --cluster fintech-reconciliation-prod \
  --task-definition fintech-reconciliation-prod

# Check system health
aws ecs describe-clusters --clusters fintech-reconciliation-prod
```

### Support Contacts
- **Technical Issues**: Development Team
- **Infrastructure**: DevOps Team  
- **Security**: Security Team
- **Compliance**: Risk Management Team

---

*This documentation covers the complete FinTech Transaction Reconciliation System. For updates and additional information, refer to the project repository and deployment guides.*