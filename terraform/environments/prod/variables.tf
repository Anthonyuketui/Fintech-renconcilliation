variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "operations_email" {
  description = "Operations team email for notifications"
  type        = string
}

variable "sender_email" {
  description = "Sender email for SES notifications"
  type        = string
}