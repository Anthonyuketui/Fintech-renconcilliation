output "rds_endpoint" {
  description = "Prod RDS PostgreSQL endpoint"
  value       = module.rds.endpoint
}

output "s3_bucket_name" {
  description = "Prod S3 bucket name"
  value       = module.s3.bucket_name
}

output "ecr_repository_url" {
  description = "Prod ECR repository URL"
  value       = module.ecs.repository_url
}

output "ecs_cluster_name" {
  description = "Prod ECS cluster name"
  value       = module.ecs.cluster_name
}