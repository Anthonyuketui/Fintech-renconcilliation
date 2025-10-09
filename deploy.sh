#!/bin/bash
# One command deployment script

set -e

echo "FinTech Reconciliation - Deploy"
echo "==============================="

# Check prerequisites
if ! command -v terraform &> /dev/null; then
    echo "ERROR: Terraform not installed. Install from: https://terraform.io"
    exit 1
fi

if ! command -v aws &> /dev/null; then
    echo "ERROR: AWS CLI not installed. Install from: https://aws.amazon.com/cli/"
    exit 1
fi

if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "ERROR: AWS credentials not configured"
    echo "Run: aws configure"
    exit 1
fi

echo "All prerequisites met"

# Step 1: Bootstrap (creates S3 + DynamoDB)
echo ""
echo "Step 1: Creating Terraform state infrastructure..."
./terraform/bootstrap.sh

# Step 2: Deploy infrastructure
echo ""
echo "Step 2: Deploying FinTech infrastructure..."
cd terraform/environments/dev
terraform init
terraform apply -auto-approve

echo ""
echo "DEPLOYMENT COMPLETE"
echo ""
echo "FinTech reconciliation system deployed to AWS"
echo ""
echo "Next steps:"
echo "1. Check ECS service: aws ecs describe-services --cluster fintech-reconciliation-dev --services fintech-reconciliation-dev"
echo "2. View logs: aws logs tail /ecs/fintech-reconciliation-dev --follow"
echo "3. Test locally: docker-compose up -d && docker-compose run --rm app python src/main.py --processors stripe"