#!/bin/bash
# Smart bootstrap - checks for existing resources first

echo "🔍 Checking for existing Terraform state resources..."

# Check if S3 bucket exists
BUCKET_NAME="fintech-reconciliation-terraform-state-$(whoami)-$(date +%s)"
aws s3 ls "s3://$BUCKET_NAME" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "❌ Bucket $BUCKET_NAME already exists"
    exit 1
fi

# Check if DynamoDB table exists  
aws dynamodb describe-table --table-name "fintech-reconciliation-terraform-locks" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "⚠️ DynamoDB table already exists - using existing table"
    USE_EXISTING_TABLE=true
else
    USE_EXISTING_TABLE=false
fi

echo "✅ Safe to proceed with bootstrap"
echo "Bucket: $BUCKET_NAME"
echo "Table: fintech-reconciliation-terraform-locks (existing: $USE_EXISTING_TABLE)"