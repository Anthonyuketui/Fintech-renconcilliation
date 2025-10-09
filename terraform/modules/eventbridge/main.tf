resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${var.project_name}-${var.environment}-reconciliation"
  description         = "Trigger reconciliation for ${var.environment}"
  schedule_expression = var.schedule_expression

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-schedule"
  })
}

resource "aws_cloudwatch_event_target" "ecs_target" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "${var.project_name}-${var.environment}-target"
  arn       = var.cluster_arn
  role_arn  = var.eventbridge_role_arn

  ecs_target {
    task_count          = 1
    task_definition_arn = var.task_definition_arn
    launch_type         = "FARGATE"
    platform_version    = "LATEST"

    network_configuration {
      subnets          = var.subnet_ids
      security_groups  = var.security_group_ids
      assign_public_ip = var.assign_public_ip
    }
  }
}