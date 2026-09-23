# CloudTrail Audit Logging Security

## Secure configuration
Enable a multi-Region CloudTrail trail that logs management events and, where needed, data
events. Deliver logs to a dedicated, access-restricted S3 bucket in a separate logging account.
Enable log file validation so tampering is detectable, and encrypt the trail with a KMS key.

## How an attack happens
Attackers who gain access frequently try to disable or delete CloudTrail (`StopLogging`,
`DeleteTrail`) or delete the log bucket to erase their tracks. Without an organization trail and
protective controls, this blinds detection.

## Prevention
- Use an organization trail managed centrally so member accounts cannot disable it.
- Protect the log bucket with a policy denying deletes and requiring the log-delivery principal.
- Enable log file integrity validation and SSE-KMS encryption.
- Alarm on CloudTrail `StopLogging` / `DeleteTrail` events via EventBridge + CloudWatch.
- Restrict who can modify trails with SCPs.

## Verification
Confirm a multi-Region org trail exists, log validation is enabled, and an alarm fires on
StopLogging.
