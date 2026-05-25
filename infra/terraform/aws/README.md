# QuantGrid AWS 3-Tier Terraform

This Terraform module defines the production target architecture for QuantGrid:

```text
Internet -> ALB public subnets -> FastAPI app EC2 private subnets -> RDS Postgres / ElastiCache Redis isolated subnets
```

The React frontend is built by CI/CD and served by Nginx or a future static hosting module. This Terraform keeps the runtime backend, database, cache, and network boundaries explicit.

## What It Creates

- VPC across configurable Availability Zones.
- Public, private app, and isolated database subnets.
- Internet Gateway and optional NAT Gateway.
- Security groups for ALB, app instances, Postgres, and Redis.
- Application Load Balancer and target group.
- EC2 launch template and Auto Scaling Group for the trading service tier.
- RDS PostgreSQL instance.
- ElastiCache Redis replication group.

## Usage

```bash
cd infra/terraform/aws
terraform init
terraform fmt -check
terraform validate
terraform plan -var-file=terraform.tfvars
```

Create `terraform.tfvars` from `terraform.tfvars.example` and provide real values through your secrets process. Do not commit `terraform.tfvars`.

## Safety Defaults

- RDS deletion protection is enabled by default.
- Database and Redis are not publicly accessible.
- Live trading is not enabled by infrastructure.
- App instances receive secrets through SSM Parameter Store paths, not plaintext Terraform variables.
