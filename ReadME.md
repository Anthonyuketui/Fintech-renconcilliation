# FinTech Transaction Reconciliation System

[![Test Coverage](https://img.shields.io/badge/coverage-81%25-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-blue.svg)]()

Transaction reconciliation system for payment processors with automated processing and cloud deployment capabilities.

## Quick Start

```bash
# Setup
cp .env.example .env
docker-compose up -d

# Run reconciliation
docker-compose run --rm app python src/main.py --processors stripe

# View results
docker-compose exec db psql -U fintech -d fintech_reconciliation -c \
  "SELECT processor_name, missing_transaction_count, total_discrepancy_amount FROM reconciliation_runs;"
```

---

## Features

- Automated transaction reconciliation across multiple payment processors
- Docker containerization with PostgreSQL database
- AWS cloud deployment with Terraform
- Comprehensive test suite (130 tests, 81% coverage)
- Security scanning and compliance
- Multi-format reporting (CSV, JSON)
- Email and Slack notifications

---

## Architecture

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

### **Component Responsibilities**
- **DataFetcher**: API integration with retry logic and pagination
- **ReconciliationEngine**: Core business logic for transaction matching
- **ReportGenerator**: Multi-format reporting with financial calculations
- **AWSManager**: Cloud storage with local fallback
- **DatabaseManager**: PostgreSQL operations with audit trails
- **NotificationService**: Multi-channel alerting (Email/Slack/SES)

---

## AWS Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   GitHub Repo   │    │  EventBridge    │    │   CloudWatch    │
│   (CI/CD)       │    │  (Scheduler)    │    │   (Monitoring)  │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                        AWS ECS Fargate                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Reconciliation  │  │ Reconciliation  │  │ Reconciliation  │ │
│  │    Task 1       │  │    Task 2       │  │    Task 3       │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────┬───────────────────┬───────────────────┬───────────────┘
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   RDS PostgreSQL│    │      S3         │    │      SES        │
│   (Multi-AZ)    │    │   (Reports)     │    │  (Notifications)│
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │reconciliation│ │    │ │   CSV/JSON  │ │    │ │   Email     │ │
│ │    _runs     │ │    │ │   Reports   │ │    │ │   Alerts    │ │
│ │missing_txns  │ │    │ │             │ │    │ │             │ │
│ │audit_logs    │ │    │ └─────────────┘ │    │ └─────────────┘ │
│ └─────────────┘ │    └─────────────────┘    └─────────────────┘
└─────────────────┘
          ▲
          │
┌─────────────────┐
│  Secrets Manager│
│                 │
│ ┌─────────────┐ │
│ │ DB Password │ │
│ │ API Keys    │ │
│ │ SMTP Config │ │
│ └─────────────┘ │
└─────────────────┘
```

## Database Schema

![ERD Diagram](Sample_Output/images/Erd.png)

The system uses PostgreSQL with the following key tables:
- `reconciliation_runs` - Tracks each reconciliation execution
- `missing_transactions` - Stores identified discrepancies
- `processor_transactions` - Cached transaction data
- `audit_logs` - Maintains compliance trails

---

## Technology Stack

### **Core Technologies**
- **Python 3.11** - Modern async/await patterns
- **PostgreSQL 15** - ACID compliance with audit trails
- **Docker & Docker Compose** - Containerized deployment
- **AWS Services** - ECS, RDS, S3, SES, EventBridge
- **Terraform** - Infrastructure as Code with 10 modules

### **Key Libraries**
- **Pydantic** - Data validation and serialization
- **Boto3** - AWS SDK integration
- **Requests** - HTTP client with retry logic
- **Pytest** - Comprehensive testing framework
- **Decimal** - Precise financial calculations

---

## Deployment Options

### **1. Local Development (Docker)**
```bash
# Quick start
docker-compose up -d
docker-compose run --rm app python src/main.py --processors stripe paypal

# With custom date
docker-compose run --rm app python src/main.py --date 2025-01-15 --processors stripe
```

### **2. AWS Cloud Deployment**
```bash
# Setup infrastructure (see SETUP.md)
# 1. Create S3 bucket and DynamoDB table
# 2. Configure backend.tf with your bucket name
# 3. Add GitHub secrets

# Deploy via CI/CD (includes security scanning, testing, and deployment)
git push origin main  # Triggers automated deployment
```

### **3. Production Scheduling**
- **EventBridge**: Automated daily execution at 4:00 AM UTC
- **ECS Fargate**: Serverless container execution
- **Multi-AZ RDS**: High availability database

---

## Test Coverage Report

| Module | Coverage | Tests | Status |
|--------|----------|-------|--------|
| **models.py** | 100% | 14 tests | ✅ Perfect |
| **reconciliation_engine.py** | 100% | 12 tests | ✅ Perfect |
| **data_fetcher.py** | 99% | 26 tests | ✅ Excellent |
| **report_generator.py** | 99% | 26 tests | ✅ Excellent |
| **notification_service.py** | 74% | 17 tests | ✅ Good |
| **database_manager.py** | 76% | 18 tests | ✅ Good |
| **aws_manager.py** | 69% | 13 tests | ✅ Acceptable |
| **main.py** | 64% | 9 tests | ✅ Acceptable |
| **TOTAL** | **81%** | **130 tests** | ✅ **Excellent** |

```bash
# Run full test suite
PYTHONPATH=src python -m pytest tests/ -v --cov=src --cov-report=term-missing

# Run specific module tests
PYTHONPATH=src python -m pytest tests/test_data_fetcher.py -v
```

---

## Security & Compliance

### **Security Features**
- ✅ **Automated Security Scanning** - Bandit + Safety in CI/CD
- ✅ **Secrets Management** - AWS Secrets Manager integration
- ✅ **Audit Trails** - Immutable PostgreSQL logs
- ✅ **Input Validation** - Path traversal and SQL injection prevention

---

## Sample Outputs

### **Email Notification**
![Email Notification](Sample_Output/images/Email-Notifications.png)

### **Database Schema**
![ERD Diagram](Sample_Output/images/Erd.png)

### **JSON Report Sample**
```json
{
  "reconciliation_summary": {
    "date": "2025-10-09",
    "processor": "stripe",
    "processor_transactions": 5000,
    "internal_transactions": 4200,
    "missing_transaction_count": 800,
    "total_discrepancy_amount": 15420.50,
    "total_volume_processed": 2500000.00
  },
  "financial_impact": {
    "discrepancy_rate": 0.16,
    "risk_level": "HIGH",
    "compliance_status": "REQUIRES_ATTENTION"
  }
}
```

---



## Documentation

### Getting Started
1. **[README.md](README.md)** - Project overview and quick start
2. **[SETUP.md](SETUP.md)** - AWS infrastructure setup
3. **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment guide

### Technical Reference
- **[TECHNICAL-DOCUMENTATION.md](TECHNICAL-DOCUMENTATION.md)** - Complete system documentation
  - Architecture and design decisions
  - Code analysis and implementation details
  - Infrastructure components
  - Security and testing strategies

### Documentation Overview
| File | Focus | Audience |
|------|-------|----------|
| README.md | Overview, features, quick start | All users |
| SETUP.md | Initial AWS configuration | DevOps, developers |
| DEPLOYMENT.md | Production deployment | DevOps, SRE |
| TECHNICAL-DOCUMENTATION.md | Complete system analysis | Engineers, architects |

---

## Development Setup

### **Prerequisites**
- Docker 20.10+ & Docker Compose 2.0+
- Python 3.11+ (for local development)
- AWS CLI (for cloud deployment)
- Terraform 1.6+ (for infrastructure)

### **Environment Configuration**
```bash
# 1. Copy environment template
cp .env.example .env

# 2. Configure required variables
DB_HOST=localhost
DB_PASSWORD=your_secure_password
OPERATIONS_EMAIL=your-email@company.com

# 3. Optional: AWS S3 integration
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_S3_BUCKET_NAME=your-bucket-name
```

### **Local Development Commands**
```bash
# Start services
docker-compose up -d

# Run tests
PYTHONPATH=src python -m pytest tests/ -v

# Run reconciliation
docker-compose run --rm app python src/main.py --processors stripe paypal square

# View logs
docker-compose logs -f app

# Database access
docker-compose exec db psql -U fintech -d fintech_reconciliation
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙋‍♂️ Support & Contact
- **Email**: uketuianthony@gmail.com

---

## Project Stats

- **Test Coverage**: 81% (130 tests)
- **Security Scans**: Automated with every commit
- **Supported Processors**: Stripe, PayPal, Square (extensible)
- **Infrastructure**: AWS ECS, RDS, Eventbridge S3 with Terraform