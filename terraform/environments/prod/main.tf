terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
  }
  
  # Backend configuration will be added after running bootstrap.sh
  # Uncomment and update after bootstrap:
  # backend "s3" {
  #   bucket         = "your-bucket-name-from-bootstrap"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "your-dynamodb-table-from-bootstrap"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Environment = "prod"
      Project     = "fintech-reconciliation"
      ManagedBy   = "terraform"
    }
  }
}

locals {
  project_name = "fintech-reconciliation"
  common_tags = {
    Environment   = "prod"
    CostCenter    = "operations"
    Owner         = "fintech-ops"
    Compliance    = "required"
    BackupPolicy  = "daily"
    Project       = "fintech-reconciliation"
    ManagedBy     = "terraform"
  }
}

# VPC Module
module "vpc" {
  source = "../../modules/vpc"

  project_name       = local.project_name
  environment        = "prod"
  enable_nat_gateway = true  # High availability
  tags              = local.common_tags
}

# S3 Module
module "s3" {
  source = "../../modules/s3"

  project_name      = local.project_name
  environment       = "prod"
  enable_versioning = true
  tags             = local.common_tags
}

# Generate random password for RDS
resource "random_password" "db_password" {
  length  = 32
  special = true
  # Only use RDS-safe special characters
  override_special = "!#$%&*+-=?_"
}

# Secrets Module
module "secrets" {
  source = "../../modules/secrets"

  project_name = local.project_name
  environment  = "prod"
  db_password  = random_password.db_password.result
  tags        = local.common_tags
}

# SES Module
module "ses" {
  source = "../../modules/ses"

  project_name     = local.project_name
  environment      = "prod"
  operations_email = var.operations_email
  sender_email     = var.sender_email
  tags            = local.common_tags
}

# Security Group
resource "aws_security_group" "ecs" {
  name_prefix = "${local.project_name}-prod-ecs-"
  vpc_id      = module.vpc.vpc_id

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS outbound for AWS services"
  }
  
  egress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP outbound for package updates"
  }

  tags = merge(local.common_tags, {
    Name = "${local.project_name}-prod-ecs-sg"
  })
}

# RDS Module
module "rds" {
  source = "../../modules/rds"

  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  ecs_security_group_id = aws_security_group.ecs.id
  
  instance_class        = "db.r5.large"
  allocated_storage     = 100
  max_allocated_storage = 1000
  password             = random_password.db_password.result
  backup_retention     = 30
  multi_az            = true
  
  project_name = local.project_name
  environment  = "prod"
  tags        = local.common_tags
}

# CloudWatch Module
module "cloudwatch" {
  source = "../../modules/cloudwatch"

  project_name   = local.project_name
  environment    = "prod"
  retention_days = 90
  tags          = local.common_tags
}

# IAM Module
module "iam" {
  source = "../../modules/iam"

  project_name    = local.project_name
  environment     = "prod"
  s3_bucket_arn   = module.s3.bucket_arn
  secrets_arn     = module.secrets.db_password_secret_arn
  tags           = local.common_tags
  
  depends_on = [module.secrets]
}

# ECS Module
module "ecs" {
  source = "../../modules/ecs"

  project_name              = local.project_name
  environment               = "prod"
  cpu                      = "2048"
  memory                   = "4096"
  execution_role_arn       = module.iam.ecs_task_execution_role_arn
  task_role_arn           = module.iam.ecs_task_role_arn
  log_group_name          = module.cloudwatch.log_group_name
  aws_region              = var.aws_region
  enable_container_insights = true
  enable_image_scanning    = true
  
  environment_variables = [
    {
      name  = "DB_HOST"
      value = module.rds.endpoint
    },
    {
      name  = "DB_PORT"
      value = "5432"
    },
    {
      name  = "DB_NAME"
      value = "fintech_reconciliation"
    },
    {
      name  = "DB_USER"
      value = "fintech"
    },
    {
      name  = "DB_PASSWORD"
      value = random_password.db_password.result
    },
    {
      name  = "AWS_S3_BUCKET_NAME"
      value = module.s3.bucket_name
    },
    {
      name  = "AWS_REGION"
      value = var.aws_region
    },
    {
      name  = "ENVIRONMENT"
      value = "prod"
    },
    {
      name  = "USE_SES"
      value = "true"
    },
    {
      name  = "SES_REGION"
      value = var.aws_region
    },
    {
      name  = "SENDER_EMAIL"
      value = var.sender_email
    },
    {
      name  = "OPERATIONS_EMAIL"
      value = var.operations_email
    }
  ]
  
  tags = local.common_tags
  depends_on = [module.cloudwatch]
}

# EventBridge Module
module "eventbridge" {
  source = "../../modules/eventbridge"

  project_name          = local.project_name
  environment           = "prod"
  schedule_expression   = "cron(0 1 * * ? *)"  # Daily at 1 AM UTC
  cluster_arn          = module.ecs.cluster_arn
  task_definition_arn  = module.ecs.task_definition_arn
  eventbridge_role_arn = module.iam.eventbridge_role_arn
  subnet_ids           = module.vpc.private_subnet_ids
  security_group_ids   = [aws_security_group.ecs.id]
  assign_public_ip     = false  # NAT gateway enabled
  tags                = local.common_tags
  
  depends_on = [module.ecs, module.iam]
}