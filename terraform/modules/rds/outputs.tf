output "endpoint" {
  description = "RDS instance endpoint"
  value       = aws_db_instance.postgres.address
}

output "security_group_id" {
  description = "RDS security group ID"
  value       = aws_security_group.rds.id
}