# Deployment Guide

## CI/CD Pipeline Deployment (Recommended)

### GitHub Secrets Required
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
- `DB_PASSWORD_DEV` / `DB_PASSWORD_PROD` 
- `OPERATIONS_EMAIL`
- `TERRAFORM_STATE_BUCKET`

### Deploy to Dev
```bash
# Automatic on main branch push
git push origin main

# Manual deployment
gh workflow run "FinTech Reconciliation - CI/CD" --field environment=dev
```

### Pipeline Stages (~35 minutes)
1. **Security Scan** (8 min) - SAST + Infrastructure + SBOM
2. **Test** (12 min) - 130 tests + performance testing
3. **Build** (10 min) - Docker build + push to ECR
4. **Deploy** (15 min) - Terraform infrastructure deployment
5. **Integration Test** (8 min) - End-to-end validation

## Manual Deployment

### Prerequisites
```bash
# Create S3 bucket and DynamoDB table
aws s3 mb s3://your-terraform-state-bucket
aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

### Deploy Infrastructure
```bash
cd terraform/environments/dev
chmod +x ../../../scripts/deploy-terraform.sh
../../../scripts/deploy-terraform.sh dev your-terraform-state-bucket us-east-1
```

### Deploy Application
```bash
# Build and push image
docker build -t fintech-reconciliation:latest .
ECR_URL=$(cd terraform/environments/dev && terraform output -raw ecr_repository_url)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_URL
docker tag fintech-reconciliation:latest $ECR_URL:latest
docker push $ECR_URL:latest
```

## Local Development

### Quick Start
```bash
cp .env.example .env
docker-compose up -d
docker-compose run --rm app python src/main.py --processors stripe
```

### Testing
```bash
# Run tests
PYTHONPATH=src pytest tests/ -v --cov=src

# Performance test
PYTHONPATH=src python scripts/performance-test.py

# Integration test
chmod +x scripts/test-integration.sh
./scripts/test-integration.sh
```

## Infrastructure Components

### AWS Resources
- **VPC** - Isolated network with public/private subnets
- **RDS PostgreSQL** - Database with automated backups
- **ECS Fargate** - Serverless container execution
- **S3** - Report storage with encryption
- **EventBridge** - Daily scheduling (4:00 AM UTC)
- **SES** - Email notifications
- **ECR** - Container registry
- **Secrets Manager** - Credential storage

### Cost Estimates
- **Dev Environment**: ~$50-100/month
- **Prod Environment**: ~$200-500/month

## Monitoring

### Health Checks
```bash
# ECS cluster status
aws ecs describe-clusters --clusters fintech-reconciliation-dev

# Database status
aws rds describe-db-instances --db-instance-identifier fintech-reconciliation-dev

# Manual task execution
aws ecs run-task --cluster fintech-reconciliation-dev --task-definition fintech-reconciliation-dev
```

### Logs
```bash
# Application logs
aws logs get-log-events --log-group-name /ecs/fintech-reconciliation-dev

# Filter errors
aws logs filter-log-events --log-group-name /ecs/fintech-reconciliation-dev --filter-pattern "ERROR"
```

## Security

### Production Checklist
- [ ] Enable MFA for AWS accounts
- [ ] Use least-privilege IAM policies
- [ ] Enable VPC Flow Logs
- [ ] Configure AWS Config for compliance
- [ ] Enable CloudTrail for audit logging
- [ ] Database in private subnets
- [ ] S3 bucket encryption enabled
- [ ] Secrets in AWS Secrets Manager

## Troubleshooting

### Common Issues
- **ECS Task Failures**: Check security groups and environment variables
- **Database Connection**: Verify RDS security group allows ECS access
- **Email Issues**: Verify SES email addresses are verified
- **Terraform Conflicts**: Use unique S3 bucket names

### Support
- Email: uketuianthony@gmail.com
- Documentation: See TECHNICAL-DOCUMENTATION.md