#!/bin/bash
# Get S3 bucket name from Terraform output for local development

cd terraform/environments/dev
BUCKET_NAME=$(terraform output -raw s3_bucket_name 2>/dev/null)

if [ $? -eq 0 ] && [ ! -z "$BUCKET_NAME" ]; then
    echo "S3 Bucket Name: $BUCKET_NAME"
    echo ""
    echo "Add this to your .env file:"
    echo "AWS_S3_BUCKET_NAME=$BUCKET_NAME"
else
    echo "Error: Could not get bucket name from Terraform."
    echo "Make sure you've deployed the infrastructure first:"
    echo "  cd terraform/environments/dev"
    echo "  terraform apply"
fi