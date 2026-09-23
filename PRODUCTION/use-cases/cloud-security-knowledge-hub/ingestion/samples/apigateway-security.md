# Amazon API Gateway Security

## Secure configuration
Protect APIs with an authorizer: Cognito JWT, a Lambda authorizer, or IAM auth. Enable
throttling (burst and steady-state rate limits) and usage plans with API keys for partners.
Front public APIs with AWS WAF (REST APIs and CloudFront-fronted APIs) to filter common attacks
and rate-limit abusive IPs. Enable access logging and execution logging to CloudWatch.

## How an attack happens
An unauthenticated or unthrottled endpoint invites scraping, brute force, and denial-of-wallet
attacks that drive up cost. Missing input validation lets injection payloads reach the backend.
Overly permissive CORS (`*`) can enable cross-site data access from malicious origins.

## Prevention
- Require an authorizer on every route; avoid open endpoints.
- Set throttling limits and usage plans; add WAF where supported.
- Restrict CORS to known origins, not `*`.
- Validate request schemas at the gateway (models/validators).
- Enable access + execution logging and alarm on 4xx/5xx spikes.

## Verification
Confirm each route has an authorizer, throttling is set, CORS is origin-scoped, and logging is on.

## Note on HTTP APIs vs WAF
AWS WAF associates with REST (v1) APIs, ALBs, AppSync, Cognito, and CloudFront — but NOT with
API Gateway HTTP (v2) APIs directly. To protect an HTTP API with WAF, front it with CloudFront
and attach the WebACL there, and rely on stage throttling at the API.
