# IAM Least-Privilege and Role Security on AWS

## Principle of least privilege
Grant only the permissions a principal needs to do its job. Start from zero and add specific
actions on specific resources, rather than using broad wildcards like `Action: "*"` or
`Resource: "*"`. Prefer managed policies scoped to a job function, and use IAM Access Analyzer
to generate least-privilege policies from CloudTrail activity.

## Roles over long-lived users
Use IAM roles with temporary STS credentials instead of IAM users with long-lived access keys.
For workloads on EC2, ECS, EKS, or Lambda, attach an execution/instance role so the service
obtains short-lived credentials automatically. Avoid embedding access keys in code or config.

## How a privilege-escalation attack happens
An attacker who obtains a low-privilege principal looks for escalation paths: `iam:PassRole`
combined with a service that assumes the passed role, `iam:CreatePolicyVersion` or
`iam:AttachUserPolicy` to grant themselves admin, or `sts:AssumeRole` into an over-trusting
role. A single wildcard permission on the IAM service is often enough to become administrator.

## Prevention
- Deny the dangerous IAM self-modification actions unless explicitly required.
- Scope `iam:PassRole` with a `Condition` on `iam:PassedToService` and specific role ARNs.
- Enable MFA for all human users and require it via policy conditions.
- Rotate access keys, or eliminate them by moving to IAM Identity Center (SSO).
- Use permission boundaries and Service Control Policies (SCPs) to cap maximum privilege.
- Review IAM Access Analyzer findings for external and cross-account access.

## Verification
Run Access Analyzer, check for unused permissions with `iam:GenerateServiceLastAccessedDetails`,
and confirm no policy grants `*:*` outside break-glass roles.
