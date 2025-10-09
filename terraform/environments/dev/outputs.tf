output "cluster_name" {
  description = "ECS cluster name"
  value       = module.ecs.cluster_name
}

output "task_definition_arn" {
  description = "ECS task definition ARN"
  value       = module.ecs.task_definition_arn
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.vpc.public_subnet_ids
}

output "ecs_security_group_id" {
  description = "ECS security group ID"
  value       = aws_security_group.ecs.id
}

output "s3_bucket_name" {
  description = "S3 bucket name"
  value       = module.s3.bucket_name
}

output "rds_endpoint" {
  description = "RDS endpoint"
  value       = module.rds.endpoint
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = module.ecs.repository_url
}

output "run_task_command" {
  description = "Command to run ECS task manually"
  value = "aws ecs run-task --cluster ${module.ecs.cluster_name} --task-definition ${module.ecs.task_definition_arn} --launch-type FARGATE --network-configuration 'awsvpcConfiguration={subnets=[${join(",", module.vpc.public_subnet_ids)}],securityGroups=[${aws_security_group.ecs.id}],assignPublicIp=ENABLED}'"
}