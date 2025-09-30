# API Documentation – FinTech Transaction Reconciliation System

This document provides detailed API-level documentation for the reconciliation system modules.

---

## **1. Models (src/models.py)**

### `Transaction`

Pydantic model representing a financial transaction.

* `transaction_id: str`
* `processor_name: str`
* `amount: Decimal`
* `currency: str`
* `status: str`
* `merchant_id: str`
* `transaction_date: datetime`
* `reference_number: str`
* `fee: Decimal`

### `ReconciliationSummary`

Summary of a reconciliation run.

* `reconciliation_date: date`
* `processor: str`
* `processor_transactions: int`
* `internal_transactions: int`
* `missing_transactions_count: int`
* `total_discrepancy_amount: Decimal`
* `total_volume_processed: Decimal`

### `ReconciliationResult`

Detailed reconciliation output.

* `reconciliation_date: date`
* `processor: str`
* `summary: ReconciliationSummary`
* `missing_transactions_details: List[Transaction]`

---

## **2. Data Fetcher (src/data_fetcher.py)**

### `DataFetcher(processor_api_base_url: str, internal_api_base_url: str, processor_name: str)`

Encapsulates external API interactions and normalization of transaction data.

#### Methods:

* `fetch_processor_data(run_date: Optional[date] = None) -> List[Transaction]`
  Fetch transactions from external payment processors (mock: `/products` API).
* `fetch_internal_data(run_date: Optional[date] = None) -> List[Transaction]`
  Fetch transactions from internal records (mock: `/posts` API).
* `close()`
  Close the session.

---

## **3. Reconciliation Engine (src/reconciliation_engine.py)**

### `ReconciliationEngine()`

Compares processor and internal transaction lists.

#### Methods:

* `reconcile(processor_transactions: List[Transaction], internal_transactions: List[Transaction], run_date: date, processor: str) -> ReconciliationResult`
  Performs reconciliation, deduplicates transaction IDs, and calculates discrepancies.

---

## **4. Report Generator (src/report_generator.py)**

### `ReportGenerator(report_prefix: str = "reconciliation_report")`

Generates structured reports from reconciliation results.

#### Methods:

* `generate_all_reports(result: ReconciliationResult, output_dir: Path) -> Tuple[Path, str, Path]`
  Creates CSV, JSON, and executive text summary.
* `_generate_detailed_csv(result: ReconciliationResult, output_dir: Path) -> Path`
  Detailed transaction CSV report.
* `_generate_executive_summary(result: ReconciliationResult) -> str`
  Human-readable summary with risk assessment.
* `_generate_json_report(result: ReconciliationResult, output_dir: Path) -> Path`
  JSON report for API consumption.
* `_calculate_financial_impact(result: ReconciliationResult) -> Dict[str, Any]`
  Calculates discrepancy rate, fees at risk, and compliance status.

---

## **5. AWS Manager (src/aws_manager.py)**

### `AWSManager()`

Handles AWS S3 and related integrations.

#### Methods:

* `upload_file_to_s3(file_path: Path, bucket_name: str, key: str) -> None`
  Uploads a local file to S3.
* `download_file_from_s3(bucket_name: str, key: str, destination: Path) -> None`
  Downloads a file from S3.

---

## **6. Database Manager (src/database_manager.py)**

### `DatabaseManager(db_url: str)`

Manages PostgreSQL connections and persistence of audit data.

#### Methods:

* `connect() -> None`
  Establish connection to PostgreSQL.
* `insert_discrepancy(record: Transaction) -> None`
  Insert a discrepancy into the database.
* `get_reconciliation_history(limit: int = 10) -> List[Dict]`
  Retrieve recent reconciliation run history.

---

## **7. Notification Service (src/notification_service.py)**

### `NotificationService(channel: str = "email")`

Dispatches alerts to operations teams.

#### Methods:

* `send_email(recipient: str, subject: str, body: str) -> None`
  Sends email alert.
* `send_slack_message(channel: str, message: str) -> None`
  Sends Slack notification.
* `send_sns_message(topic_arn: str, message: str) -> None`
  Publishes alert to AWS SNS.

---

## **8. Main Runner (src/main.py)**

Entry point for running reconciliations.

#### CLI Example:

```bash
python src/main.py --processors stripe paypal
```

#### Flow:

1. Fetch processor + internal data.
2. Run reconciliation.
3. Generate reports.
4. Store reports in DB and S3.
5. Send notifications.

---
