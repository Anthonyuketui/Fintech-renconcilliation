variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment (dev/prod)"
  type        = string
}

variable "operations_email" {
  description = "Operations team email address"
  type        = string
}

variable "sender_email" {
  description = "Sender email address for notifications"
  type        = string
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}