#!/bin/bash
set -e

echo "🧪 Integration Test - FinTech Reconciliation System"

# AWS credentials should be set via environment or AWS CLI profile
# export AWS_ACCESS_KEY_ID=your_access_key
# export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1

APP="fintech-reconciliation-dev"

echo "Looking for resources for: $APP"

# Get VPC ID
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=$APP-vpc" --query 'Vpcs[0].VpcId' --output text)
if [[ "$VPC_ID" == "None" || -z "$VPC_ID" ]]; then
  echo "ERROR: VPC not found for $APP-vpc"
  exit 1
fi
echo "Found VPC: $VPC_ID"

# Get Subnet ID
SUBNET_ID=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:Name,Values=*public*" --query 'Subnets[0].SubnetId' --output text)
if [[ "$SUBNET_ID" == "None" || -z "$SUBNET_ID" ]]; then
  echo "ERROR: Public subnet not found in VPC $VPC_ID"
  exit 1
fi
echo "Found Subnet: $SUBNET_ID"

# Get Security Group ID
SG_ID=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:Name,Values=$APP-ecs-sg" --query 'SecurityGroups[0].GroupId' --output text)
if [[ "$SG_ID" == "None" || -z "$SG_ID" ]]; then
  echo "Trying alternative security group lookup..."
  SG_ID=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=*ecs*" --query 'SecurityGroups[0].GroupId' --output text)
fi
if [[ "$SG_ID" == "None" || -z "$SG_ID" ]]; then
  echo "ERROR: ECS security group not found in VPC $VPC_ID"
  aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" --query 'SecurityGroups[*].{GroupId:GroupId,GroupName:GroupName,Tags:Tags}' --output table
  exit 1
fi
echo "Found Security Group: $SG_ID"

# Run reconciliation task
echo "Starting ECS task..."
TASK_ARN=$(aws ecs run-task \
  --cluster $APP \
  --task-definition $APP \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"'$APP'","command":["python","src/main.py","--processors","stripe","--date","'$(date +%Y-%m-%d)'"]}]}' \
  --query 'tasks[0].taskArn' --output text)

if [[ "$TASK_ARN" == "None" || -z "$TASK_ARN" ]]; then
  echo "ERROR: Failed to start ECS task"
  exit 1
fi
echo "Task started: $TASK_ARN"

# Wait and check result
echo "Waiting for task to complete..."
aws ecs wait tasks-stopped --cluster $APP --tasks $TASK_ARN
EXIT_CODE=$(aws ecs describe-tasks --cluster $APP --tasks $TASK_ARN --query 'tasks[0].containers[0].exitCode' --output text)

echo "Task completed with exit code: $EXIT_CODE"

if [ "$EXIT_CODE" = "0" ]; then
  echo "✅ Integration test passed - Reconciliation completed successfully!"
else
  echo "❌ Integration test failed with exit code: $EXIT_CODE"
  echo "Task details:"
  aws ecs describe-tasks --cluster $APP --tasks $TASK_ARN --query 'tasks[0].containers[0]' --output json
  exit 1
fi