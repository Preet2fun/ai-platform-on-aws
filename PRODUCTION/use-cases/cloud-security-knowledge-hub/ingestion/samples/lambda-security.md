# Securing AWS Lambda Functions

## Execution role least privilege
Each Lambda function assumes an execution role. Scope that role to only the actions the
function needs — a specific S3 prefix, one DynamoDB table, one Secrets Manager secret. Never
attach broad policies like AdministratorAccess or `s3:*` to a function role.

## Environment variables and secrets
Do not store secrets in plaintext environment variables. Use AWS Secrets Manager or SSM
Parameter Store (SecureString) and fetch at runtime, or use Lambda's integration to inject
them. Encrypt environment variables with a customer-managed KMS key when they hold sensitive
configuration.

## How an attack happens
An attacker who finds an over-permissioned function role can use the function as a pivot: a
code vulnerability (e.g. unsafe deserialization or SSRF) lets them run code with the role's
permissions and reach other AWS resources. Publicly exposed function URLs without auth are a
direct entry point.

## Prevention
- Set Lambda function URL auth type to AWS_IAM, never NONE, unless truly public.
- Validate and sanitize all event input; treat every trigger as untrusted.
- Keep dependencies patched; scan for vulnerable packages in CI.
- Put functions that reach private data inside a VPC with least-privilege security groups.
- Enable AWS X-Ray and CloudWatch logs; alert on unusual invocation patterns or errors.

## Verification
Confirm no function URL uses AuthType NONE unintentionally, review each execution role for
wildcards, and check that environment variables contain no secrets.
