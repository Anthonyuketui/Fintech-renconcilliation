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
  
  # Backend configured in backend.tf
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
    Environment = "prod"
    CostCenter  = "production"
    Owner       = "ops-team"
    Project     = "fintech-reconciliation"
    ManagedBy   = "terraform"
  }
}

module "vpc" {
  source = "../../modules/vpc"

  project_name       = local.project_name
  environment        = "prod"
  enable_nat_gateway = true  # Production needs NAT Gateway for security
  tags              = local.common_tags
}

module "s3" {
  source = "../../modules/s3"

  project_name      = local.project_name
  environment       = "prod"
  enable_versioning = true  # Production needs versioning
  tags             = local.common_tags
}

resource "random_password" "db_password" {
  length  = 32
  special = true
  # Only use RDS-safe special characters
  override_special = "!#$%&*+-=?_"
}

module "secrets" {
  source = "../../modules/secrets"

  project_name = local.project_name
  environment  = "prod"
  db_password  = var.db_password  # Use provided password for prod
  tags        = local.common_tags
}

module "ses" {
  source = "../../modules/ses"

  project_name     = local.project_name
  environment      = "prod"
  operations_email = var.operations_email
  sender_email     = var.sender_email
  tags            = local.common_tags
}

resource "aws_security_group" "ecs" {
  name        = "${local.project_name}-prod-ecs-sg"
  vpc_id      = module.vpc.vpc_id

  # Restrict outbound traffic to specific ports only
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # trivy:ignore:AVD-AWS-0104
    description = "HTTPS for AWS APIs"
  }
  
  egress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr]
    description = "PostgreSQL database access"
  }
  
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    self        = true
    description = "PostgreSQL access from ECS tasks"
  }

  tags = merge(local.common_tags, {
    Name = "${local.project_name}-prod-ecs-sg"
  })
}

module "rds" {
  source = "../../modules/rds"

  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.private_subnet_ids  # Use private subnets in prod
  ecs_security_group_id = aws_security_group.ecs.id
  
  instance_class        = "db.t3.small"     # Larger instance for prod
  allocated_storage     = 100               # More storage for prod
  max_allocated_storage = 1000              # Higher max storage
  password             = var.db_password
  backup_retention     = 30                 # Longer retention for prod
  multi_az            = true                # Multi-AZ for prod availability
  
  project_name = local.project_name
  environment  = "prod"
  tags        = local.common_tags
}

module "cloudwatch" {
  source = "../../modules/cloudwatch"

  project_name   = local.project_name
  environment    = "prod"
  retention_days = 90  # Longer retention for prod
  tags          = local.common_tags
}

module "iam" {
  source = "../../modules/iam"

  project_name    = local.project_name
  environment     = "prod"
  s3_bucket_arn   = module.s3.bucket_arn
  secrets_arn     = module.secrets.db_password_secret_arn
  tags           = local.common_tags
  
  depends_on = [module.secrets]
}

module "ecs" {
  source = "../../modules/ecs"

  project_name              = local.project_name
  environment               = "prod"
  cpu                      = "1024"  # More CPU for prod
  memory                   = "2048"  # More memory for prod
  execution_role_arn       = module.iam.ecs_task_execution_role_arn
  task_role_arn           = module.iam.ecs_task_role_arn
  log_group_name          = module.cloudwatch.log_group_name
  aws_region              = var.aws_region
  enable_container_insights = true   # Enable insights for prod
  enable_image_scanning    = true
  image_tag_mutability     = "IMMUTABLE"  # Immutable for prod security
  
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
      value = var.db_password
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

module "eventbridge" {
  source = "../../modules/eventbridge"

  project_name          = local.project_name
  environment           = "prod"
  schedule_expression   = "cron(0 4 * * ? *)"  # Same schedule as dev
  cluster_arn          = module.ecs.cluster_arn
  task_definition_arn  = module.ecs.task_definition_arn
  eventbridge_role_arn = module.iam.eventbridge_role_arn
  subnet_ids           = module.vpc.private_subnet_ids  # Use private subnets in prod
  security_group_ids   = [aws_security_group.ecs.id]
  assign_public_ip     = false  # No public IP in prod
  tags                = local.common_tags
  
  depends_on = [module.ecs, module.iam]
}