# AWS Secrets Manager Best Practices

## Secure configuration
Store credentials, API keys, and database passwords in AWS Secrets Manager rather than in code,
environment variables, or config files. Encrypt secrets with a customer-managed KMS key, scope
resource policies to the specific roles that need each secret, and enable automatic rotation
with a rotation Lambda where the target supports it.

## How an attack happens
Hardcoded secrets in source control, container images, or Lambda environment variables are the
most common leak. An attacker who reads them gains direct access to databases and third-party
APIs. Overly broad `secretsmanager:GetSecretValue` on `Resource: "*"` lets a compromised role
read every secret in the account.

## Prevention
- Never commit secrets; scan repos and images with secret scanners in CI.
- Scope `GetSecretValue` to specific secret ARNs, not `*`.
- Enable automatic rotation and a customer-managed KMS key per sensitivity tier.
- Use VPC endpoints for Secrets Manager so retrieval stays on the AWS network.
- Audit access with CloudTrail; alert on unusual GetSecretValue volume.

## Verification
Confirm no secrets in code/images, rotation is enabled, and IAM grants are ARN-scoped.
