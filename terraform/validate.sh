#!/bin/bash

# Terraform Validation Script

echo "🔍 Validating Terraform Configuration..."

# Check if AWS CLI is configured
echo "Checking AWS credentials..."
if ! aws sts get-caller-identity &>/dev/null; then
    echo "❌ AWS credentials not configured. Run 'aws configure'"
    exit 1
fi
echo "✅ AWS credentials configured"

# Check if Terraform is installed
echo "Checking Terraform installation..."
if ! command -v terraform &>/dev/null; then
    echo "❌ Terraform not installed. Download from https://terraform.io/downloads"
    exit 1
fi
echo "✅ Terraform installed: $(terraform version -json | jq -r .terraform_version)"

# Validate each environment
for env in dev prod; do
    echo "Validating $env environment..."
    
    cd "environments/$env" || exit 1
    
    # Check if terraform.tfvars exists
    if [ ! -f "terraform.tfvars" ]; then
        echo "⚠️  terraform.tfvars missing in $env. Copy from terraform.tfvars.example"
    else
        echo "✅ terraform.tfvars found in $env"
    fi
    
    # Initialize and validate
    terraform init -backend=false &>/dev/null
    if terraform validate &>/dev/null; then
        echo "✅ $env configuration valid"
    else
        echo "❌ $env configuration invalid"
        terraform validate
    fi
    
    cd ../..
done

echo "🎉 Validation complete!"
echo ""
echo "Next steps:"
echo "1. Copy terraform.tfvars.example to terraform.tfvars in each environment"
echo "2. Edit terraform.tfvars with your database passwords"
echo "3. Run: ./deploy.sh dev plan"