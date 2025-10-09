resource "aws_cloudwatch_log_group" "main" {
  name              = "/ecs/${var.project_name}-${var.environment}"
  retention_in_days = var.retention_days

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-logs"
  })
}