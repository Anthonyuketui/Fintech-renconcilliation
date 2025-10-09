output "ses_policy_arn" {
  description = "ARN of the SES send policy"
  value       = aws_iam_policy.ses_send_policy.arn
}

output "configuration_set_name" {
  description = "Name of the SES configuration set"
  value       = aws_ses_configuration_set.main.name
}

output "operations_email_identity" {
  description = "Operations email identity ARN"
  value       = aws_ses_email_identity.operations.arn
}

output "sender_email_identity" {
  description = "Sender email identity ARN"
  value       = aws_ses_email_identity.sender.arn
}