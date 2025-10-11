# Setup Instructions

## 1. Create AWS Resources

```bash
# Create S3 bucket (replace with unique name)
aws s3 mb s3://fintech-terraform-state-1760119671

# Create DynamoDB table
aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

## 2. Configure Terraform Backend

```bash
# Copy and configure backend for each environment
cp terraform/environments/dev/backend.tf.example terraform/environments/dev/backend.tf
cp terraform/environments/prod/backend.tf.example terraform/environments/prod/backend.tf

# Edit backend.tf files and replace YOUR_BUCKET_NAME_HERE with your actual bucket name
```

## 3. Configure GitHub Secrets

Add these secrets to your GitHub repository:

- `AWS_ACCESS_KEY_ID` - Your AWS access key
- `AWS_SECRET_ACCESS_KEY` - Your AWS secret key  
- `DB_PASSWORD_DEV` - Database password for dev
- `DB_PASSWORD_PROD` - Database password for prod
- `OPERATIONS_EMAIL` - Your email for notifications

## 4. Deploy

Push to main branch or run workflow manually.

## Cleanup

```bash
# Delete resources when done
aws s3 rb s3://your-bucket-name --force
aws dynamodb delete-table --table-name terraform-locks
```