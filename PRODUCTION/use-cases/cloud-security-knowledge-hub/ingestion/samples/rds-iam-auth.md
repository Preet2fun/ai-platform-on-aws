# RDS IAM Database Authentication

## Secure configuration
Enable IAM database authentication on RDS/Aurora (MySQL and PostgreSQL) so applications connect
using short-lived IAM auth tokens instead of static database passwords. Grant the connecting
role `rds-db:connect` scoped to a specific database user resource ARN. Continue to require TLS.

## How an attack happens
Static database passwords stored in application config or leaked from a repo give an attacker
durable access. Long-lived DB credentials are hard to rotate and easy to reuse.

## Prevention
- Turn on IAM database authentication; issue 15-minute auth tokens at connect time.
- Scope `rds-db:connect` to the exact `dbuser` resource ARN, not `*`.
- Enforce TLS and keep the instance private (no public accessibility).
- For the master password, store it in Secrets Manager with rotation.
- Audit connections via database and CloudTrail logs.

## Verification
Confirm IAM auth is enabled, the app uses auth tokens (no static password), and `rds-db:connect`
is ARN-scoped.
