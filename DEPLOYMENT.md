# Deployment Guide

## Prerequisites
- AWS CLI configured (`aws configure`)
- Terraform installed
- Docker installed

## Option 1: One Command Deployment (Recommended)
```bash
# Everything automated - just run this:
./deploy.sh
```

## Option 2: CI/CD Auto-Deploy
```bash
# Just push - CI/CD handles everything including bootstrap
git add .
git commit -m "Deploy FinTech system"
git push origin main
```

## Option 3: Manual Steps
```bash
# Step 1: Bootstrap
./terraform/bootstrap.sh

# Step 2: Deploy
cd terraform/environments/dev
terraform init
terraform apply
```

## Option 3: Skip Remote State (Simplest)
```bash
# Remove backend configuration
rm terraform/environments/dev/backend.tf

# Deploy with local state
cd terraform/environments/dev
terraform init
terraform apply
```

## Local Development Only
```bash
# Skip AWS entirely
docker-compose up -d
docker-compose run --rm app python src/main.py --processors stripe
```

## Troubleshooting
- **Bucket exists**: Use Option 2 or 3
- **No AWS access**: Use local development
- **Permission denied**: Check IAM permissions