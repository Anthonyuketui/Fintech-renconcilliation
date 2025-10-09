# GitHub Secrets Setup

## Required Repository Secrets
Go to GitHub → Settings → Secrets and variables → Actions

### Repository Secrets:
```
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
```

### Environment Secrets:

**Dev Environment (`dev`):**
```
DB_PASSWORD_DEV=any_secure_password_32_chars
```

**Prod Environment (`prod`):**
```
DB_PASSWORD_PROD=different_secure_password_32_chars
```

## Setup Steps:
1. Create AWS IAM user with programmatic access
2. Attach policies: EC2FullAccess, ECSFullAccess, RDSFullAccess, S3FullAccess, IAMFullAccess
3. Add secrets to GitHub repository
4. Create environments in GitHub (Settings → Environments)
5. Push to main branch to trigger deployment

## Email Verification:
After first deployment, verify your email in AWS SES:
```bash
aws ses verify-email-identity --email-address uketuianthony@gmail.com
```