variable "project_name" {
  description = "Project name used for resource naming."
  type        = string
  default     = "quantgrid"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "ap-south-1"
}

variable "az_count" {
  description = "Number of Availability Zones to use."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3."
  }
}

variable "vpc_cidr" {
  description = "VPC CIDR block."
  type        = string
  default     = "10.40.0.0/16"
}

variable "allowed_http_cidrs" {
  description = "CIDR blocks allowed to reach the public ALB."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "enable_nat_gateway" {
  description = "Whether private app subnets should route egress through NAT."
  type        = bool
  default     = true
}

variable "app_ami_id" {
  description = "AMI ID for QuantGrid app instances. Build and promote AMIs through CI/CD."
  type        = string
}

variable "app_instance_type" {
  description = "EC2 instance type for app instances."
  type        = string
  default     = "t3.small"
}

variable "app_desired_capacity" {
  description = "Desired app instance count."
  type        = number
  default     = 2
}

variable "app_min_size" {
  description = "Minimum app instance count."
  type        = number
  default     = 2
}

variable "app_max_size" {
  description = "Maximum app instance count."
  type        = number
  default     = 4
}

variable "app_port" {
  description = "Port exposed by the FastAPI app service."
  type        = number
  default     = 8000
}

variable "app_ssm_env_path" {
  description = "SSM Parameter Store path prefix containing runtime app environment values."
  type        = string
  default     = "/quantgrid/staging/app/"
}

variable "db_name" {
  description = "Postgres database name."
  type        = string
  default     = "quantgrid"
}

variable "db_username" {
  description = "Postgres master username."
  type        = string
  default     = "quantgrid"
}

variable "db_password" {
  description = "Postgres master password. Supply through CI/CD secret variables or Terraform Cloud."
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  description = "Allocated RDS storage in GB."
  type        = number
  default     = 20
}

variable "db_deletion_protection" {
  description = "Enable RDS deletion protection."
  type        = bool
  default     = true
}

variable "redis_node_type" {
  description = "ElastiCache Redis node type."
  type        = string
  default     = "cache.t4g.micro"
}
