# Protecting EC2 Instance Metadata Service (IMDS) from SSRF

## What IMDS is
The EC2 Instance Metadata Service exposes instance data and, when an instance profile is
attached, temporary IAM credentials at the link-local address 169.254.169.254. IMDSv1 is a
request/response model with no session token, which makes it reachable by any process that can
issue an HTTP request from the instance.

## How an SSRF attack on IMDS happens
A server-side request forgery (SSRF) vulnerability lets an attacker coerce an application into
making an HTTP request to an attacker-chosen URL. If the app is running on EC2 with IMDSv1, the
attacker points the request at http://169.254.169.254/latest/meta-data/iam/security-credentials/
and reads the role's temporary credentials. Those credentials are then used to call AWS APIs
with the instance role's permissions, often leading to privilege escalation and data theft.

## How to prevent it
- Require IMDSv2 (token-based sessions). Set HttpTokens to "required" so every metadata request
  must first obtain a session token via PUT, which SSRF payloads typically cannot perform.
- Set the metadata hop limit to 1 so containers cannot reach IMDS through the host.
- Disable IMDS entirely on instances that do not need instance-profile credentials.
- Fix the underlying SSRF: validate and allowlist outbound URLs, block link-local ranges.
- Scope instance-profile IAM roles to least privilege so a leaked credential is low-value.

## Verification
Confirm HttpTokens=required and HttpPutResponseHopLimit=1 in the instance metadata options, and
test that a plain GET to the credentials path without a token is rejected.
