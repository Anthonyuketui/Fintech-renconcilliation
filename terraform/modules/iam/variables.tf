variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment (dev/prod)"
  type        = string
}

variable "s3_bucket_arn" {
  description = "S3 bucket ARN for IAM policies"
  type        = string
}

variable "secrets_arn" {
  description = "Secrets Manager ARN for IAM policies"
  type        = string
}



variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}