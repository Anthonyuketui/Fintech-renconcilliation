#!/bin/bash
# One-command bootstrap for maximum implementability

set -e

echo "FinTech Reconciliation - Bootstrap"
echo "================================="

# Check AWS credentials
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "ERROR: AWS credentials not configured"
    echo "Run: aws configure"
    exit 1
fi

# Get AWS account ID for uniqueness
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_DEFAULT_REGION:-us-east-1}

echo "AWS Account: $ACCOUNT_ID"
echo "Region: $REGION"

# Check for existing resources
echo ""
echo "Checking for existing Terraform state resources..."

# Look for any existing terraform state buckets
EXISTING_BUCKETS=$(aws s3api list-buckets --query "Buckets[?contains(Name, 'terraform-state')].Name" --output text 2>/dev/null || echo "")

if [ ! -z "$EXISTING_BUCKETS" ]; then
    echo "WARNING: Found existing Terraform state buckets:"
    echo "$EXISTING_BUCKETS"
    echo ""
    read -p "Do you want to use an existing bucket? (y/N): " use_existing
    
    if [[ $use_existing =~ ^[Yy]$ ]]; then
        echo "Please manually configure terraform/environments/*/backend.tf with your existing bucket"
        exit 0
    fi
fi

# Create unique resources
cd terraform/bootstrap
REGION=${AWS_DEFAULT_REGION:-us-east-1}

echo ""
echo "Creating Terraform state infrastructure..."

# Initialize and apply
terraform init
terraform apply -auto-approve

# Get outputs
BUCKET_NAME=$(terraform output -raw s3_bucket_name)
DYNAMODB_TABLE=$(terraform output -raw dynamodb_table_name)

echo ""
echo "Bootstrap Complete"
echo "S3 Bucket: $BUCKET_NAME"
echo "DynamoDB Table: $DYNAMODB_TABLE"

# Auto-update backend.tf files
echo ""
echo "Auto-configuring backend files..."

for env in dev prod; do
    BACKEND_FILE="../environments/$env/backend.tf"
    if [ -f "$BACKEND_FILE" ]; then
        cat > "$BACKEND_FILE" << EOF
terraform {
  backend "s3" {
    bucket         = "$BUCKET_NAME"
    key            = "fintech-reconciliation/$env/terraform.tfstate"
    region         = "$REGION"
    dynamodb_table = "$DYNAMODB_TABLE"
    encrypt        = true
  }
}
EOF
        echo "Updated $BACKEND_FILE"
    fi
done

echo ""
echo "Ready to deploy! Run:"
echo "cd terraform/environments/dev && terraform init && terraform apply"