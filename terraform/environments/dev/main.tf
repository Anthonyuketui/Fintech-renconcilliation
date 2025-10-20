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
      Environment = "dev"
      Project     = "fintech-reconciliation"
      ManagedBy   = "terraform"
    }
  }
}

locals {
  project_name = "fintech-reconciliation"
  common_tags = {
    Environment = "dev"
    CostCenter  = "development"
    Owner       = "dev-team"
    Project     = "fintech-reconciliation"
    ManagedBy   = "terraform"
  }
}

module "vpc" {
  source = "../../modules/vpc"

  project_name       = local.project_name
  environment        = "dev"
  enable_nat_gateway = false
  tags              = local.common_tags
}

module "s3" {
  source = "../../modules/s3"

  project_name      = local.project_name
  environment       = "dev"
  enable_versioning = false
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
  environment  = "dev"
  db_password  = random_password.db_password.result
  tags        = local.common_tags
}

module "ses" {
  source = "../../modules/ses"

  project_name     = local.project_name
  environment      = "dev"
  operations_email = var.operations_email
  sender_email     = var.sender_email
  tags            = local.common_tags
}

resource "aws_security_group" "ecs" {
  name_prefix = "${local.project_name}-dev-ecs-"
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
    cidr_blocks = ["10.0.0.0/16"]
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
    Name = "${local.project_name}-dev-ecs-sg"
  })
}

module "rds" {
  source = "../../modules/rds"

  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.public_subnet_ids  # Use public subnets in dev for cost savings
  ecs_security_group_id = aws_security_group.ecs.id
  
  instance_class        = "db.t3.micro"
  allocated_storage     = 20
  max_allocated_storage = 100
  password             = random_password.db_password.result
  backup_retention     = 7
  multi_az            = false
  
  project_name = local.project_name
  environment  = "dev"
  tags        = local.common_tags
}

module "cloudwatch" {
  source = "../../modules/cloudwatch"

  project_name   = local.project_name
  environment    = "dev"
  retention_days = 7
  tags          = local.common_tags
}

module "iam" {
  source = "../../modules/iam"

  project_name    = local.project_name
  environment     = "dev"
  s3_bucket_arn   = module.s3.bucket_arn
  secrets_arn     = module.secrets.db_password_secret_arn
  tags           = local.common_tags
  
  depends_on = [module.secrets]
}

module "ecs" {
  source = "../../modules/ecs"

  project_name              = local.project_name
  environment               = "dev"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = module.iam.ecs_task_execution_role_arn
  task_role_arn           = module.iam.ecs_task_role_arn
  log_group_name          = module.cloudwatch.log_group_name
  aws_region              = var.aws_region
  enable_container_insights = false
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
      value = "dev"
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
  environment           = "dev"
  schedule_expression   = "cron(0 4 * * ? *)"
  cluster_arn          = module.ecs.cluster_arn
  task_definition_arn  = module.ecs.task_definition_arn
  eventbridge_role_arn = module.iam.eventbridge_role_arn
  subnet_ids           = module.vpc.public_subnet_ids  # Use public subnets in dev
  security_group_ids   = [aws_security_group.ecs.id]
  assign_public_ip     = true  # Need public IP in dev
  tags                = local.common_tags
  
  depends_on = [module.ecs, module.iam]
}

