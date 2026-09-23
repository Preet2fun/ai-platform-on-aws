# SNS and SQS Access Policy Security

## Secure configuration
SNS topics and SQS queues have resource policies. Scope them to specific principals and source
ARNs. Enable server-side encryption (SSE-KMS) for message data at rest and enforce TLS in
transit with an `aws:SecureTransport` condition. For cross-service triggers, use a condition on
`aws:SourceArn` so only the intended source can publish or send.

## How an attack happens
A topic or queue policy with `Principal: "*"` and no conditions lets anyone on the internet
publish messages (spam, injection into downstream processing) or, for SQS, receive and delete
messages — leading to data leakage or message loss.

## Prevention
- Never use `Principal: "*"` without tight `aws:SourceArn`/`aws:SourceAccount` conditions.
- Enable SSE-KMS and deny non-TLS requests.
- Grant send/receive to specific roles only; separate producer and consumer permissions.
- Audit policies with IAM Access Analyzer for public or cross-account access.

## Verification
Confirm no topic/queue is world-writable, SSE is enabled, and non-TLS is denied.
