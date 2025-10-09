#!/bin/bash

# Terraform Deployment Script for FinTech Reconciliation System

set -e

ENVIRONMENT=${1:-dev}
ACTION=${2:-plan}

if [[ ! "$ENVIRONMENT" =~ ^(dev|prod)$ ]]; then
    echo "Usage: $0 <dev|prod> [plan|apply|destroy]"
    echo "Example: $0 dev plan"
    exit 1
fi

if [[ ! "$ACTION" =~ ^(plan|apply|destroy)$ ]]; then
    echo "Invalid action. Use: plan, apply, or destroy"
    exit 1
fi

ENV_DIR="environments/$ENVIRONMENT"

if [ ! -d "$ENV_DIR" ]; then
    echo "Environment directory $ENV_DIR not found"
    exit 1
fi

echo "🚀 Deploying to $ENVIRONMENT environment..."
echo "📁 Working directory: $ENV_DIR"

cd "$ENV_DIR"

# Check if terraform.tfvars exists
if [ ! -f "terraform.tfvars" ]; then
    echo "⚠️  terraform.tfvars not found. Creating from example..."
    if [ -f "terraform.tfvars.example" ]; then
        cp terraform.tfvars.example terraform.tfvars
        echo "📝 Please edit terraform.tfvars with your values before proceeding"
        exit 1
    else
        echo "❌ terraform.tfvars.example not found"
        exit 1
    fi
fi

# Initialize Terraform
echo "🔧 Initializing Terraform..."
terraform init || { echo "❌ Terraform init failed"; exit 1; }

# Validate configuration
echo "✅ Validating configuration..."
terraform validate || { echo "❌ Terraform validation failed"; exit 1; }

# Execute action
case $ACTION in
    plan)
        echo "📋 Planning deployment..."
        terraform plan || { echo "❌ Terraform plan failed"; exit 1; }
        ;;
    apply)
        echo "🚀 Applying changes..."
        terraform apply || { echo "❌ Terraform apply failed"; exit 1; }
        ;;
    destroy)
        echo "⚠️  WARNING: This will destroy all infrastructure in $ENVIRONMENT environment!"
        read -p "Are you sure? Type 'yes' to continue: " confirm
        if [ "$confirm" = "yes" ]; then
            echo "💥 Destroying infrastructure..."
            terraform destroy || { echo "❌ Terraform destroy failed"; exit 1; }
        else
            echo "🛑 Destroy cancelled"
            exit 0
        fi
        ;;
esac

echo "✅ $ACTION completed for $ENVIRONMENT environment"