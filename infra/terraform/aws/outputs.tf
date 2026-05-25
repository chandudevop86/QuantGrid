output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.main.id
}

output "alb_dns_name" {
  description = "Public ALB DNS name."
  value       = aws_lb.app.dns_name
}

output "app_target_group_arn" {
  description = "App target group ARN."
  value       = aws_lb_target_group.app.arn
}

output "postgres_endpoint" {
  description = "Postgres endpoint."
  value       = aws_db_instance.postgres.address
  sensitive   = true
}

output "redis_primary_endpoint" {
  description = "Redis primary endpoint."
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}
