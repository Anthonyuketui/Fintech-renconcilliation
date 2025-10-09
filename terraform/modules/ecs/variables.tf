variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment (dev/prod)"
  type        = string
}

variable "cpu" {
  description = "ECS task CPU units"
  type        = string
  default     = "512"
}

variable "memory" {
  description = "ECS task memory in MB"
  type        = string
  default     = "1024"
}

variable "execution_role_arn" {
  description = "ECS task execution role ARN"
  type        = string
}

variable "task_role_arn" {
  description = "ECS task role ARN"
  type        = string
}

variable "environment_variables" {
  description = "Environment variables for container"
  type        = list(object({
    name  = string
    value = string
  }))
  default = []
}

variable "log_group_name" {
  description = "CloudWatch log group name"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "enable_container_insights" {
  description = "Enable container insights"
  type        = bool
  default     = false
}

variable "enable_image_scanning" {
  description = "Enable ECR image scanning"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}