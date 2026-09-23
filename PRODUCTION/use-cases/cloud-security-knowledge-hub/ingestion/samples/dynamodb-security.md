# Securing Amazon DynamoDB

## Encryption and access control
DynamoDB encrypts all tables at rest by default. For sensitive workloads, use a customer-managed
KMS key so you control rotation and can audit key usage via CloudTrail. Control access with
fine-grained IAM policies: scope `dynamodb:GetItem`, `PutItem`, and `Query` to specific table
ARNs, and use IAM condition keys like `dynamodb:LeadingKeys` to restrict a principal to only
its own partition-key items (row-level access).

## How an attack happens
An over-permissive IAM policy granting `dynamodb:*` on `Resource: "*"` lets a compromised
principal read or delete every table in the account. Applications that build queries from
unvalidated user input can be coerced into scanning or reading items beyond their intended
scope. Point-in-time recovery being disabled means a malicious `DeleteTable` is unrecoverable.

## Prevention
- Scope IAM to specific table ARNs and actions; never grant `dynamodb:*` on `*`.
- Use `dynamodb:LeadingKeys` conditions for per-tenant row-level isolation.
- Enable point-in-time recovery (PITR) and on-demand backups.
- Use VPC endpoints for DynamoDB so traffic stays on the AWS network.
- Enable CloudTrail data events for DynamoDB to audit item-level access.

## Verification
Confirm no IAM policy grants `dynamodb:*` on `*`, PITR is enabled, and access uses table-scoped
ARNs with condition keys where per-tenant isolation is required.
