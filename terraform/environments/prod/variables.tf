variable "aws_region" {
  description = "AWS region for prod environment"
  type        = string
  default     = "us-east-1"
}

variable "operations_email" {
  description = "Operations team email for notifications"
  type        = string
}

variable "sender_email" {
  description = "Sender email for notifications"
  type        = string
}

