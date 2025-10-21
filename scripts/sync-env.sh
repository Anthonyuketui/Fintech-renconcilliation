#!/bin/bash
# Sync environment configuration from Terraform outputs
# Usage: ./scripts/sync-env.sh [dev|prod]

ENV=${1:-dev}
ENV_FILE=".env"
TERRAFORM_DIR="terraform/environments/$ENV"

if [ ! -d "$TERRAFORM_DIR" ]; then
    echo "Error: Environment '$ENV' not found"
    exit 1
fi

echo "Syncing $ENV environment configuration..."

cd "$TERRAFORM_DIR"

# Get values from Terraform
BUCKET_NAME=$(terraform output -raw s3_bucket_name 2>/dev/null)
RDS_ENDPOINT=$(terraform output -raw rds_endpoint 2>/dev/null)

cd - > /dev/null

if [ -z "$BUCKET_NAME" ]; then
    echo "Warning: Could not get S3 bucket name. Infrastructure may not be deployed."
    exit 1
fi

# Update .env file
sed -i.bak "s/^AWS_S3_BUCKET_NAME=.*/AWS_S3_BUCKET_NAME=$BUCKET_NAME/" "$ENV_FILE"

if [ ! -z "$RDS_ENDPOINT" ]; then
    sed -i.bak "s/^DB_HOST=.*/DB_HOST=$RDS_ENDPOINT/" "$ENV_FILE"
fi

echo "✅ Updated .env with $ENV environment values:"
echo "   S3 Bucket: $BUCKET_NAME"
[ ! -z "$RDS_ENDPOINT" ] && echo "   RDS Host: $RDS_ENDPOINT"

rm -f "$ENV_FILE.bak"