# FinTech Transaction Reconciliation System

Automated daily reconciliation system for payment processor transactions with PostgreSQL audit trails, AWS S3 archival, and intelligent alerting. Built for production deployment with Docker.

---

## Quick Start (5 Minutes)

```bash
# 1. Clone and setup
git clone <repository-url>
cd fintech-reconciliation
cp .env.example .env

# 2. Start services
docker-compose up -d

# 3. Wait for database initialization
sleep 20

# 4. Run reconciliation
docker-compose run --rm app python src/main.py --processors stripe --date 2025-09-30

# 5. Verify results
docker-compose exec db psql -U fintech -d fintech_reconciliation -c \
  "SELECT processor_name, missing_transaction_count, status FROM reconciliation_runs;"
```

**Expected Output:** 1 completed reconciliation run with ~5 missing transactions identified.

---

## Overview

This system automates the reconciliation of transactions between payment processors (Stripe, PayPal, Square) and internal FinTech databases. It identifies discrepancies, generates settlement reports, and sends notifications to the operations team.

### Business Impact

- Reduces manual reconciliation from 4+ hours to < 5 minutes
- Ensures 99.9% accuracy for compliance requirements
- Provides automated audit trails for regulators
- Improves real-time decision-making with alerts

### Key Features

- **Containerized deployment** with Docker Compose
- **PostgreSQL audit trails** with row-level security
- **AWS S3 integration** with local fallback
- **Email notifications** with HTML reports
- **Comprehensive logging** with structured JSON output
- **Data validation** with automated quality checks

---

## Architecture

```text
┌─────────────────┐
│   CLI Entry     │
│    (main.py)    │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│   ReconciliationSystem (Core)       │
└────┬──────┬──────┬──────┬──────┬────┘
     │      │      │      │      │
     ▼      ▼      ▼      ▼      ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│Data  │ │Reconc│ │Report│ │AWS   │ │DB    │
│Fetch │ │Engine│ │Gen   │ │Mgr   │ │Mgr   │
└──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘
   │        │        │        │        │
   ▼        ▼        ▼        ▼        ▼
┌────────────────────────────────────────┐
│  External APIs │ S3 │ PostgreSQL       │
└────────────────────────────────────────┘
```

### Component Responsibilities

- **DataFetcher**: Retrieves and normalizes transactions from APIs/CSV
- **ReconciliationEngine**: Compares datasets and identifies discrepancies
- **ReportGenerator**: Produces JSON/CSV reports with summaries
- **AWSManager**: Handles S3 upload/download with presigned URLs
- **DatabaseManager**: Manages PostgreSQL operations with audit trail
- **NotificationService**: Sends email notifications with report attachments

---

## Docker Deployment

### Why Docker?

This system is designed for containerized deployment to ensure:

- **Production parity**: Development environment matches production exactly
- **Simplified setup**: One command vs. manual PostgreSQL installation, Python setup, etc.
- **Database automation**: `setup.sql` is optimized for Docker's initialization process
- **Consistent environments**: Same behavior across all machines

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum
- 10GB disk space

### Container Services

- `db`: PostgreSQL 15 with auto-initialization from setup.sql
- `app`: Python application with reconciliation engine

### Docker Commands

```bash
# Start all services
docker-compose up -d

# View application logs
docker-compose logs -f app

# Stop services
docker-compose down

# Stop and remove volumes (fresh start)
docker-compose down -v

# Rebuild after code changes
docker-compose build app
docker-compose up -d
```

### Database Access

```bash
# Interactive PostgreSQL shell
docker-compose exec db psql -U fintech -d fintech_reconciliation

# Run SQL query
docker-compose exec db psql -U fintech -d fintech_reconciliation -c \
  "SELECT * FROM reconciliation_runs ORDER BY start_time DESC LIMIT 10;"

# Execute SQL file
docker-compose exec -T db psql -U fintech -d fintech_reconciliation < my_script.sql
```

---

## Environment Configuration

Create `.env` file (copy from `.env.example`):

```ini
# Database (Required)
DB_HOST=db
DB_PORT=5432
DB_NAME=fintech_reconciliation
DB_USER=fintech
DB_PASSWORD=fintech

# AWS S3 (Optional - falls back to local storage)
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_S3_BUCKET_NAME=fintech-reports
AWS_REGION=us-east-1

# Email Notifications (Optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USER=your_email@company.com
EMAIL_PASSWORD=your_app_password
OPERATIONS_EMAIL=ops@fintech.com

# APIs (Mock data sources)
PROCESSOR_API_BASE_URL=https://dummyjson.com
INTERNAL_API_BASE_URL=https://jsonplaceholder.typicode.com
```

### Configuration Notes

- System works without AWS credentials (uses local file storage as fallback)
- Email notifications are optional (skipped if SMTP not configured)
- For Gmail: Enable 2FA and generate App Password at https://myaccount.google.com/apppasswords

---

## Usage

### Running Reconciliation

```bash
# Single processor, today's date
docker-compose run --rm app python src/main.py --processors stripe

# Multiple processors
docker-compose run --rm app python src/main.py --processors stripe paypal square

# Specific date
docker-compose run --rm app python src/main.py --date 2025-09-30 --processors stripe
```

### Verification Commands

```bash
# Check reconciliation results
docker-compose exec db psql -U fintech -d fintech_reconciliation -c \
  "SELECT run_date, processor_name, missing_transaction_count, 
          total_discrepancy_amount, status 
   FROM reconciliation_runs 
   ORDER BY start_time DESC LIMIT 10;"

# View missing transactions
docker-compose exec db psql -U fintech -d fintech_reconciliation -c \
  "SELECT transaction_id, amount, merchant_id, transaction_date
   FROM missing_transactions 
   WHERE reconciliation_run_id IN (
     SELECT id FROM reconciliation_runs ORDER BY start_time DESC LIMIT 1
   );"

# Check reports directory
ls -la Sample_Output/stripe_2025-09-30/
```

### Scheduled Execution

For production deployments, use cron:

```bash
# Add to crontab (crontab -e)
0 1 * * * cd /opt/fintech-reconciliation && \
  docker-compose run --rm app python src/main.py \
  --processors stripe paypal square >> /var/log/reconciliation.log 2>&1
```

---

## Reports & Outputs

### Report Types

**1. CSV Reports** - Detailed transaction-level data
   - Path: `Sample_Output/{processor}_{date}/reconciliation_report_{processor}_{date}.csv`
   - Contains: All missing transactions with full details

**2. JSON Reports** - API-friendly format with summary
   - Path: `Sample_Output/{processor}_{date}/reconciliation_report_{processor}_{date}.json`
   - Contains: Summary statistics + missing transaction array

**3. Database Records** - Full audit trail
   - `reconciliation_runs`: Run metadata and status
   - `missing_transactions`: Discrepancy details
   - `audit_log`: All system actions logged

**4. S3 Objects** - Uploaded if AWS configured
   - Organized by date: `reports/YYYY-MM-DD/`
   - Presigned URLs for secure access (24-hour expiry)

### Sample Email Notification

**Subject:** Daily Reconciliation Report - STRIPE - 2025-09-30  

**Body (HTML Rendered):**

![Sample Email Screenshot](Sample_Output/Email-Notifications.png)

### Sample JSON Output

```json
{
  "report_metadata": {
    "generated_at": "2025-09-30T19:04:23",
    "system_version": "1.0.0"
  },
  "reconciliation_summary": {
    "date": "2025-09-30",
    "processor": "stripe",
    "processor_transactions": 30,
    "internal_transactions": 24,
    "missing_transaction_count": 6,
    "total_discrepancy_amount": 255.44,
    "total_volume_processed": 6577.50
  },
  "missing_transactions": [
    {
      "transaction_id": "TXN_STRIPE_20250930_0026",
      "amount": 0.99,
      "currency": "USD",
      "merchant_id": "GROCERIES",
      "transaction_date": "2025-09-30T14:30:00Z"
    }
  ],
  "financial_impact": {
    "discrepancy_rate": 0.20,
    "risk_level": "LOW",
    "compliance_status": "COMPLIANT"
  }
}
```

---

## Database Schema

### Tables Overview

- **reconciliation_runs** - Run metadata with status tracking
- **missing_transactions** - Discrepancies per run with full details
- **audit_log** - Immutable audit trail for compliance
- **data_quality_checks** - Validation results per run
- **system_health** - Component health monitoring
- **system_configuration** - Application settings

### Key Features

- UUIDs for all primary keys
- JSONB columns for flexible metadata storage
- Check constraints for business logic enforcement
- Triggers for automatic audit logging and validation
- Indexes optimized for common query patterns
- Row-level security enabled

### Entity Relationship Diagram

[ERD Diagram](Sample_Output/ERD.png)

### Useful Queries

```sql
-- Recent reconciliation summary
SELECT * FROM v_recent_reconciliations LIMIT 10;

-- High-value discrepancies
SELECT * FROM v_high_value_missing_transactions;

-- Daily metrics (last 7 days)
SELECT * FROM v_daily_reconciliation_metrics 
WHERE run_date >= CURRENT_DATE - INTERVAL '7 days';

-- System health status
SELECT * FROM system_health 
ORDER BY check_time DESC LIMIT 10;
```

---

## Testing

### Running Tests

```bash
# Run all tests
docker-compose run --rm app pytest tests/ -v

# With coverage report
docker-compose run --rm app pytest --cov=src tests/

# Specific test file
docker-compose run --rm app pytest tests/test_reconciliation_engine.py -v
```

### Test Coverage

```
tests/test_data_fetcher.py ................ 11 tests
tests/test_reconciliation_engine.py ....... 12 tests
tests/test_report_generator.py ............ 26 tests

Total: 49 tests passing in ~18 seconds
```

**Core Business Logic Coverage:**
- ReconciliationEngine: 100%
- ReportGenerator: 100%
- DataFetcher: 88%
- Models: 95%

### Test Categories

- **Unit Tests**: Individual component validation (DataFetcher, ReconciliationEngine)
- **Integration Tests**: Report generation, file I/O operations
- **Edge Cases**: Empty datasets, duplicate IDs, large dataset performance
- **Business Logic**: Financial calculations, risk level determination

---

## Monitoring & Observability

### Application Logs

```bash
# Real-time logs
docker-compose logs -f app

# Filter errors only
docker-compose logs app | grep ERROR

# Export logs for analysis
docker-compose logs --no-color app > reconciliation.log
```

### Database Monitoring

```sql
-- Recent reconciliation runs
SELECT * FROM v_recent_reconciliations LIMIT 10;

-- High-value discrepancies (>$1000)
SELECT * FROM v_high_value_missing_transactions;

-- Daily metrics (last 7 days)
SELECT * FROM v_daily_reconciliation_metrics 
WHERE run_date >= CURRENT_DATE - INTERVAL '7 days';

-- System health status
SELECT * FROM system_health 
ORDER BY check_time DESC LIMIT 10;
```

### Health Checks

```bash
# Database connectivity
docker-compose exec db pg_isready -U fintech

# Container health status
docker-compose ps
```

---

## Troubleshooting

### Database Connection Issues

```bash
# Check if database is running
docker-compose ps db

# View database logs
docker-compose logs db | tail -50

# Test connection
docker-compose exec db psql -U fintech -d fintech_reconciliation -c "SELECT 1;"

# Reset database (WARNING: deletes all data)
docker-compose down -v
docker-compose up -d db
sleep 20
```

### Import/Module Errors

```bash
# Rebuild container with fresh dependencies
docker-compose build --no-cache app
docker-compose up -d
```

### Report Generation Issues

```bash
# Check Sample_Output directory permissions
ls -la Sample_Output/

# Create directory manually if missing
mkdir -p Sample_Output
chmod 755 Sample_Output

# Verify recent reports
find Sample_Output -name "*.csv" -mtime -1
```

### AWS S3 Upload Failures

The system gracefully falls back to local storage if S3 is unavailable. Check logs for:

```
AWS credentials invalid or bucket inaccessible. Using local fallback.
```

To enable S3:
1. Add AWS credentials to `.env`
2. Ensure IAM user has `s3:PutObject` and `s3:GetObject` permissions
3. Verify bucket exists and is in the correct region

---

## Performance

### Scalability Features

- **O(1) lookup complexity**: ReconciliationEngine uses hash maps for transaction matching
- **Bulk inserts**: Missing transactions inserted in batches
- **Connection pooling**: Database connections reused across operations
- **Indexed queries**: All common queries have covering indexes

### Tested Performance

- 10,000 transactions reconciled in < 2 seconds
- 1M transaction dataset handled in < 30 seconds
- Database queries return in < 100ms
- Memory usage: ~200MB for typical workloads

---

## Security

### Security Checklist

- [ ] `.env` file in `.gitignore` (never commit credentials)
- [ ] PostgreSQL password changed from default
- [ ] AWS IAM roles with minimum required permissions
- [ ] SMTP credentials use app-specific passwords
- [ ] Database backups configured
- [ ] SSL/TLS enabled for database connections in production

### Database Security

The schema includes:
- Row-level security (RLS) policies
- Immutable audit log (cannot be modified after 1 minute)
- Role-based access control (reader, writer, admin roles)
- Check constraints preventing invalid data

---

## Project Structure

```
fintech-reconciliation/
├── src/
│   ├── __init__.py
│   ├── main.py                    # CLI entry point
│   ├── models.py                  # Data models
│   ├── data_fetcher.py           # API integration
│   ├── reconciliation_engine.py  # Core business logic
│   ├── report_generator.py       # Report creation
│   ├── notification_service.py   # Email alerts
│   ├── database_manager.py       # PostgreSQL operations
│   └── aws_manager.py            # S3 integration
├── tests/
│   ├── test_data_fetcher.py
│   ├── test_reconciliation_engine.py
│   └── test_report_generator.py
├── Sample_Output/                # Generated reports
├── docker-compose.yml            # Multi-container orchestration
├── Dockerfile                    # Application container
├── setup.sql                     # Database schema
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment template
└── README.md                     # This file
```

---

## Dependencies

```
boto3==1.34.0              # AWS SDK
psycopg2-binary==2.9.9     # PostgreSQL adapter
requests==2.31.0           # HTTP client
pandas==2.1.4              # Data manipulation
python-dotenv==1.0.0       # Environment management
pytest==7.4.0              # Testing framework
```


## Support

For issues or questions:

1. Check the **Troubleshooting** section above
2. Review application logs: `docker-compose logs app`
3. Check database status: `docker-compose ps`
4. Open GitHub issue with:
   - Error messages from logs
   - Steps to reproduce
   - Environment details (OS, Docker version)

---

