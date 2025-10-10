#!/bin/bash

# Clean up existing AWS resources to allow fresh Terraform deployment
set -e

ENV=${1:-dev}
echo "Cleaning up existing resources for environment: $ENV"

# Delete CloudWatch Log Group
aws logs delete-log-group --log-group-name "/ecs/fintech-reconciliation-$ENV" 2>/dev/null || echo "Log group not found"

# Delete RDS DB Subnet Group
aws rds delete-db-subnet-group --db-subnet-group-name "fintech-reconciliation-$ENV-db-subnet-group" 2>/dev/null || echo "DB subnet group not found"

# Delete Secrets Manager Secret
aws secretsmanager delete-secret --secret-id "fintech-reconciliation-$ENV-db-password" --force-delete-without-recovery 2>/dev/null || echo "Secret not found"

# Delete SES Configuration Set
aws ses delete-configuration-set --configuration-set-name "fintech-reconciliation-$ENV-config-set" 2>/dev/null || echo "SES config set not found"

echo "Cleanup completed. Terraform can now create resources cleanly."