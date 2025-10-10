#!/bin/bash

# Import existing AWS resources into Terraform state
# This script imports resources that already exist in AWS but are missing from the state file

set -e

echo "Importing existing AWS resources into Terraform state..."

# Import CloudWatch Log Group
echo "Importing CloudWatch Log Group..."
terraform import module.cloudwatch.aws_cloudwatch_log_group.main /ecs/fintech-reconciliation-dev || echo "CloudWatch log group import failed or already exists in state"

# Import RDS DB Subnet Group
echo "Importing RDS DB Subnet Group..."
terraform import module.rds.aws_db_subnet_group.main fintech-reconciliation-dev-db-subnet-group || echo "DB subnet group import failed or already exists in state"

# Import Secrets Manager Secret
echo "Importing Secrets Manager Secret..."
terraform import module.secrets.aws_secretsmanager_secret.db_password fintech-reconciliation-dev-db-password || echo "Secret import failed or already exists in state"

# Import SES Configuration Set
echo "Importing SES Configuration Set..."
terraform import module.ses.aws_ses_configuration_set.main fintech-reconciliation-dev-config-set || echo "SES config set import failed or already exists in state"

echo "Import completed. Running terraform plan to verify state..."
terraform plan