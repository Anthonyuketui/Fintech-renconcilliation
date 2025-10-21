#!/bin/bash
set -e

TARGET_ENV=$1
TERRAFORM_STATE_BUCKET=$2
AWS_REGION=$3

cd terraform/environments/$TARGET_ENV

cat > backend.tf << EOF
terraform {
  backend "s3" {
    bucket         = "$TERRAFORM_STATE_BUCKET"
    key            = "$TARGET_ENV/terraform.tfstate"
    region         = "$AWS_REGION"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
EOF

terraform init -input=false -reconfigure
terraform apply -input=false -lock-timeout=30m -auto-approve