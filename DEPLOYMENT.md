# FinTech Reconciliation System - Deployment Guide

## Overview

This system supports multiple deployment strategies from local development to enterprise production with automated CI/CD pipelines.

---

## Prerequisites

### Required Tools
- **AWS CLI** (v2.0+) - `aws configure` with appropriate credentials
- **Terraform** (v1.6+) - Infrastructure as Code
- **Docker** (v20.10+) - Container runtime
- **Git** - Version control and CI/CD triggers

### Required AWS Permissions
- **S3**: Bucket creation, object management
- **RDS**: Database instance management
- **ECS**: Cluster and task management
- **IAM**: Role and policy management
- **VPC**: Network configuration
- **EventBridge**: Scheduling configuration
- **SES**: Email service configuration

---

## Deployment Options

### Option 1: Automated CI/CD Deployment (Recommended for Production)

**Setup GitHub Secrets:**
```bash
# Required secrets in GitHub repository settings:
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
DB_PASSWORD_DEV=secure_dev_password_32_chars
DB_PASSWORD_PROD=secure_prod_password_32_chars
OPERATIONS_EMAIL=your-email@company.com
TERRAFORM_STATE_BUCKET=your-unique-terraform-state-bucket
```

**Deploy to Development:**
```bash
# Automatic deployment on main branch push
git add .
git commit -m "Deploy FinTech reconciliation system"
git push origin main

# Manual deployment with environment selection
gh workflow run "FinTech Reconciliation - CI/CD" --field environment=dev
```

**Deploy to Production:**
```bash
# Manual production deployment (requires approval)
gh workflow run "FinTech Reconciliation - CI/CD" --field environment=prod
```

**Pipeline Stages (58 minutes total):**
1. **Security Scan** (8 min) - Semgrep SAST + Trivy vulnerability scanning + SBOM generation
2. **Test & Quality Gates** (12 min) - 130 tests + performance testing with PostgreSQL service
3. **Build & Package** (10 min) - Docker image creation + container security scan
4. **Deploy Infrastructure** (15 min) - Terraform apply + drift detection with 10 modules
5. **Verify Deployment** (5 min) - Health checks and deployment validation
6. **Integration Test** (8 min) - End-to-end system validation

### Option 2: Manual Infrastructure Deployment

**Step 1: Bootstrap Terraform State Management**
```bash
# Create S3 bucket for Terraform state (one-time setup)
aws s3 mb s3://your-terraform-state-bucket-unique-name
aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

**Step 2: Configure Backend**
```bash
# Create backend configuration
cat > terraform/environments/dev/backend.tf << EOF
terraform {
  backend "s3" {
    bucket         = "your-terraform-state-bucket-unique-name"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
EOF
```

**Step 3: Deploy Infrastructure**
```bash
cd terraform/environments/dev

# Initialize Terraform with backend
terraform init -reconfigure

# Plan deployment (review changes)
terraform plan -var="db_password=your_secure_password" \
               -var="operations_email=your-email@company.com" \
               -var="sender_email=your-email@company.com"

# Apply infrastructure
terraform apply -var="db_password=your_secure_password" \
                -var="operations_email=your-email@company.com" \
                -var="sender_email=your-email@company.com"
```

**Step 4: Deploy Application**
```bash
# Build and push Docker image
docker build -t fintech-reconciliation:latest .

# Get ECR repository URL from Terraform output
ECR_URL=$(terraform output -raw ecr_repository_url)

# Authenticate with ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $ECR_URL

# Tag and push image
docker tag fintech-reconciliation:latest $ECR_URL:latest
docker push $ECR_URL:latest
```

### Option 3: Local Development Setup

**Quick Start:**
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your local settings
# DB_HOST=localhost
# DB_PASSWORD=your_local_password
# OPERATIONS_EMAIL=your-email@company.com

# Start local services
docker-compose up -d

# Run reconciliation
docker-compose run --rm app python src/main.py --processors stripe paypal square

# View results
docker-compose exec db psql -U fintech -d fintech_reconciliation \
  -c "SELECT processor_name, missing_transaction_count, total_discrepancy_amount FROM reconciliation_runs;"
```

**Development Commands:**
```bash
# Run tests
PYTHONPATH=src python -m pytest tests/ -v --cov=src

# Run specific processor
docker-compose run --rm app python src/main.py --processors stripe --date 2025-01-15

# View logs
docker-compose logs -f app

# Database access
docker-compose exec db psql -U fintech -d fintech_reconciliation

# Reset environment
docker-compose down -v && docker-compose up -d
```

---

## Infrastructure Components

### AWS Resources Created
- **VPC**: Isolated network with public/private subnets
- **RDS PostgreSQL**: Multi-AZ database with automated backups
- **ECS Fargate**: Serverless container execution
- **S3 Bucket**: Report storage with versioning
- **IAM Roles**: Least-privilege access for services
- **EventBridge**: Daily scheduling (4:00 AM UTC)
- **SES**: Email notification service
- **CloudWatch**: Logging and monitoring
- **Secrets Manager**: Secure credential storage
- **ECR**: Container image registry

### Terraform Modules (10 total)
```
terraform/
├── modules/
│   ├── vpc/           # Network infrastructure
│   ├── rds/           # PostgreSQL database
│   ├── ecs/           # Container orchestration
│   ├── s3/            # Object storage
│   ├── iam/           # Access management
│   ├── eventbridge/   # Scheduling
│   ├── ses/           # Email service
│   ├── cloudwatch/    # Monitoring
│   ├── secrets/       # Credential management
│   └── ecr/           # Container registry
└── environments/
    ├── dev/           # Development environment
    └── prod/          # Production environment
```

---

## Configuration Management

### Environment Variables
```bash
# Database Configuration
DB_HOST=fintech-reconciliation-dev.cluster-xyz.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=fintech_reconciliation
DB_USER=fintech
DB_PASSWORD=<from_secrets_manager>

# AWS Configuration
AWS_S3_BUCKET_NAME=fintech-reconciliation-dev-reports
AWS_REGION=us-east-1
USE_SES=true

# Email Configuration
SENDER_EMAIL=noreply@company.com
OPERATIONS_EMAIL=ops@company.com
SES_REGION=us-east-1

# Application Configuration
ENVIRONMENT=dev
PROCESSOR_API_BASE_URL=https://fakestoreapi.com
INTERNAL_API_BASE_URL=https://jsonplaceholder.typicode.com
```

### Email Verification (Required for SES)
```bash
# Verify sender email address
aws ses verify-email-identity --email-address your-email@company.com --region us-east-1

# Check verification status
aws ses get-identity-verification-attributes \
  --identities your-email@company.com \
  --region us-east-1
```

---

## Monitoring Strategy

### Development Environment
**Local Prometheus/Grafana Stack:**
```bash
# Start monitoring with reconciliation system
docker-compose up -d

# Access monitoring interfaces
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin/admin123)

# Query database metrics
pg_stat_database_tup_inserted{datname="fintech_reconciliation"}
pg_stat_user_tables_n_tup_ins{relname="missing_transactions"}
```

### Production Environment
**AWS Native Monitoring (Secure & Compliant):**
- **CloudWatch**: RDS metrics, ECS container health, application logs
- **RDS Performance Insights**: Database query analysis and optimization
- **Database-driven Business Metrics**: Reconciliation results stored in PostgreSQL
- **Email Notifications**: Immediate alerts for CRITICAL/HIGH severity issues

**Key Production Metrics:**
```bash
# Database performance
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=fintech-reconciliation-dev

# ECS task health
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=fintech-reconciliation-dev

# Business metrics from database
psql -h <rds-endpoint> -U fintech -d fintech_reconciliation \
  -c "SELECT COUNT(*) as total_runs, AVG(missing_transaction_count) as avg_missing FROM reconciliation_runs WHERE created_at > NOW() - INTERVAL '30 days';"
```

---

## Monitoring & Operations

### Health Checks
```bash
# ECS cluster status
aws ecs describe-clusters --clusters fintech-reconciliation-dev

# Task definition status
aws ecs describe-task-definition --task-definition fintech-reconciliation-dev

# Database connectivity and performance
aws rds describe-db-instances --db-instance-identifier fintech-reconciliation-dev

# RDS Performance Insights (production monitoring)
aws pi get-resource-metrics \
  --service-type RDS \
  --identifier <db-resource-id> \
  --metric-queries file://metrics-query.json

# S3 bucket access
aws s3 ls s3://fintech-reconciliation-dev-reports/

# CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=fintech-reconciliation-dev
```

### Manual Task Execution
```bash
# Run reconciliation manually
aws ecs run-task \
  --cluster fintech-reconciliation-dev \
  --task-definition fintech-reconciliation-dev \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"fintech-reconciliation-dev","command":["python","src/main.py","--processors","stripe","--date","2025-01-15"]}]}'

# Check task status
aws ecs describe-tasks --cluster fintech-reconciliation-dev --tasks <task-arn>
```

### Log Analysis
```bash
# View application logs
aws logs get-log-events \
  --log-group-name /ecs/fintech-reconciliation-dev \
  --log-stream-name <stream-name>

# Filter error logs
aws logs filter-log-events \
  --log-group-name /ecs/fintech-reconciliation-dev \
  --filter-pattern "ERROR"
```

---

## Troubleshooting

### Common Issues

**1. Terraform State Conflicts**
```bash
# Solution: Use unique bucket names or separate workspaces
terraform workspace new dev
terraform workspace select dev
```

**2. ECS Task Failures**
```bash
# Check task logs
aws ecs describe-tasks --cluster fintech-reconciliation-dev --tasks <task-arn>

# Common causes:
# - Database connectivity (check security groups)
# - Missing environment variables
# - Image pull failures (check ECR permissions)
```

**3. Database Connection Issues**
```bash
# Test connectivity from ECS task
aws ecs run-task \
  --cluster fintech-reconciliation-dev \
  --task-definition fintech-reconciliation-dev \
  --overrides '{"containerOverrides":[{"name":"fintech-reconciliation-dev","command":["python","-c","from src.database_manager import DatabaseManager; dm = DatabaseManager(); print(dm.health_check())"]}]}'
```

**4. Email Delivery Issues**
```bash
# Check SES sending statistics
aws ses get-send-statistics --region us-east-1

# Verify email address status
aws ses get-identity-verification-attributes \
  --identities your-email@company.com
```

### Performance Optimization
- **Database**: Use connection pooling, optimize queries
- **ECS**: Adjust CPU/memory allocation based on workload
- **S3**: Enable transfer acceleration for large reports
- **Monitoring**: Set up CloudWatch alarms for key metrics

---

## Security Considerations

### Production Checklist
- [ ] Enable MFA for AWS accounts
- [ ] Use least-privilege IAM policies
- [ ] Enable VPC Flow Logs
- [ ] Configure AWS Config for compliance
- [ ] Set up AWS GuardDuty for threat detection
- [ ] Enable CloudTrail for audit logging
- [ ] Use AWS Secrets Manager for all credentials
- [ ] Enable S3 bucket encryption and versioning
- [ ] Configure RDS encryption at rest
- [ ] Set up backup and disaster recovery procedures

### Network Security
- Database in private subnets only
- ECS tasks with minimal security group rules
- S3 bucket policies restricting access
- VPC endpoints for AWS services (optional)

---

## Cost Optimization

### Development Environment (~$50-100/month)
- **RDS**: db.t3.micro with 20GB storage
- **ECS**: 0.5 vCPU, 1GB memory (pay per use)
- **S3**: Standard storage with lifecycle policies
- **Other services**: Minimal usage charges

### Production Environment (~$200-500/month)
- **RDS**: db.t3.small with Multi-AZ, automated backups
- **ECS**: Auto-scaling based on demand
- **S3**: Intelligent tiering for cost optimization
- **CloudWatch**: Extended retention and detailed monitoring

### Cost Reduction Tips
- Use Spot instances for non-critical workloads
- Implement S3 lifecycle policies
- Schedule ECS tasks to run only when needed
- Monitor and optimize resource utilization

---

## Support & Maintenance

### Regular Maintenance Tasks
- **Weekly**: Review CloudWatch metrics and logs
- **Monthly**: Update container images and dependencies
- **Quarterly**: Review and rotate credentials
- **Annually**: Disaster recovery testing

### Backup Strategy
- **Database**: Automated daily backups (7-day retention)
- **Reports**: S3 versioning and cross-region replication
- **Infrastructure**: Terraform state backup
- **Application**: Container images in ECR

This deployment guide reflects the actual sophisticated infrastructure and CI/CD pipeline we built, providing multiple deployment options for different use cases and environments.