# Securing Amazon S3 Buckets

## Block public access
Amazon S3 provides account-level and bucket-level Block Public Access settings. Enable all
four settings (BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy, RestrictPublicBuckets)
unless you have an explicit, reviewed reason to expose objects publicly. Block Public Access
overrides any conflicting bucket policy or ACL, which makes it a reliable guardrail against
accidental exposure.

## Encrypt data at rest
Enable default encryption on every bucket. Prefer SSE-KMS with a customer-managed key (CMK)
when you need audit logging of key usage and independent key rotation. SSE-S3 (AES-256) is
acceptable for lower-sensitivity data. Encryption in transit should be enforced with a bucket
policy that denies requests where aws:SecureTransport is false.

## Least-privilege access
Grant access through IAM roles and bucket policies scoped to specific prefixes and actions.
Avoid wildcard principals. Use VPC endpoints for S3 so traffic stays on the AWS network, and
add a condition on aws:SourceVpce to restrict access to the intended VPC endpoint.

## How a public-exposure attack happens
An attacker enumerates bucket names or finds a misconfigured bucket policy that allows
s3:GetObject to a wildcard principal. If Block Public Access is disabled and objects are not
encrypted with a restrictive key policy, the attacker downloads sensitive objects directly.
Bucket takeover can also occur when a dangling DNS record points to a deleted bucket name that
the attacker re-creates.

## Prevention checklist
- Turn on Block Public Access at the account and bucket level.
- Enable default SSE-KMS encryption and deny non-TLS requests.
- Enable S3 server access logging or CloudTrail data events for audit.
- Use Access Analyzer for S3 to detect buckets shared externally.
- Remove unused buckets and stale DNS records to prevent takeover.
