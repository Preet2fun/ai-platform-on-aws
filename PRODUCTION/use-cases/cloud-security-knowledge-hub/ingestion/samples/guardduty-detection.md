# Amazon GuardDuty Threat Detection

## Secure configuration
Enable GuardDuty in every Region and account, managed centrally through an AWS Organizations
delegated administrator. Turn on the relevant protection plans (S3, EKS, malware, RDS, Lambda)
for your workloads. Route findings to a central security account via EventBridge and Security
Hub for triage.

## What it detects
GuardDuty analyzes CloudTrail, VPC Flow Logs, and DNS logs to detect threats: credential
exfiltration (e.g. instance-role credentials used from an external IP), cryptomining,
reconnaissance, and communication with known-malicious hosts.

## Prevention and response
- Enable organization-wide, all-Region coverage with auto-enable for new accounts.
- Forward findings to Security Hub + a SIEM; alert on high-severity findings.
- Automate response with EventBridge (isolate an instance, revoke sessions) for known patterns.
- Suppress noisy benign findings with suppression rules, not by disabling detectors.

## Verification
Confirm GuardDuty is enabled in all Regions/accounts and high-severity findings page on-call.
