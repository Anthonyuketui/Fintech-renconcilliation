resource "aws_ses_email_identity" "operations" {
  email = var.operations_email
}

resource "aws_ses_email_identity" "sender" {
  email = var.sender_email
}

resource "aws_ses_configuration_set" "main" {
  name = "${var.project_name}-${var.environment}-config-set"
}

resource "aws_iam_policy" "ses_send_policy" {
  name        = "${var.project_name}-${var.environment}-ses-send-policy"
  description = "Policy to allow sending emails via SES"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = [
          aws_ses_email_identity.operations.arn,
          aws_ses_email_identity.sender.arn,
          "arn:aws:ses:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:configuration-set/${aws_ses_configuration_set.main.name}"
        ]
      }
    ]
  })

  tags = var.tags
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}