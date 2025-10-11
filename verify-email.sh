#!/bin/bash

echo "Setting up SES email verification..."

# Your operations email
OPERATIONS_EMAIL="uketuianthony@gmail.com"

echo "Step 1: Verify email address in SES"
aws ses verify-email-identity --email-address "$OPERATIONS_EMAIL" --region us-east-1

echo "✅ Verification email sent to $OPERATIONS_EMAIL"
echo "📧 Check your inbox and click the verification link!"

echo ""
echo "Step 2: Check verification status"
aws ses get-identity-verification-attributes --identities "$OPERATIONS_EMAIL" --region us-east-1

echo ""
echo "Step 3: Test email sending (run after verification)"
echo "aws ses send-email \\"
echo "  --source \"$OPERATIONS_EMAIL\" \\"
echo "  --destination \"ToAddresses=$OPERATIONS_EMAIL\" \\"
echo "  --message \"Subject={Data='Test Email'},Body={Text={Data='Test message'}}\" \\"
echo "  --region us-east-1"

echo ""
echo "After verifying your email, the reconciliation system will send notifications when discrepancies are found."