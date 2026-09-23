# Preventing Public Exposure of Amazon RDS Databases

## The risk
An Amazon RDS instance becomes internet-reachable when it is launched with
PubliclyAccessible=true and its security group allows the database port (for example 5432 or
3306) from 0.0.0.0/0. Combined with weak or default credentials, this is a direct path to data
theft. Automated scanners continuously probe public IP ranges for open database ports.

## How the attack unfolds
An attacker scans for open database ports on public RDS endpoints, finds one reachable from the
internet, and attempts credential stuffing or exploits a known engine vulnerability. Once
connected, they exfiltrate data or pivot deeper into the environment.

## Secure configuration
- Set PubliclyAccessible=false; place RDS in private subnets with no route to an internet gateway.
- Restrict the security group to the specific application security group, never 0.0.0.0/0.
- Require TLS for connections and rotate credentials via Secrets Manager.
- Enable storage encryption with KMS and enable automated backups.
- Enable enhanced monitoring and CloudWatch alarms on unusual connection counts.

## Prevention checklist
- Confirm no RDS instance has PubliclyAccessible=true unless explicitly required and reviewed.
- Audit security groups for database ports open to the internet.
- Use AWS Config rules (rds-instance-public-access-check) to detect drift.
