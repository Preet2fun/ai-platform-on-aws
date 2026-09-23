# EBS Volume and Snapshot Exposure

## Secure configuration
Encrypt EBS volumes and snapshots by default (enable account-level EBS encryption by default
with a customer-managed KMS key). Keep snapshots private; never mark them public. Share
snapshots only with specific account IDs when required.

## How an attack happens
A snapshot accidentally shared publicly, or made available to an unknown account, lets an
attacker create a volume from it and read its entire contents — often including credentials,
tokens, and source code. Attackers actively scan for public EBS/RDS snapshots.

## Prevention
- Enable EBS encryption by default; use a customer-managed KMS key.
- Block public sharing; audit snapshot `createVolumePermission` for `all` or unknown accounts.
- Use AWS Config rules (ebs-snapshot-public-restorable-check) to detect exposure.
- Restrict `ec2:ModifySnapshotAttribute` to a small set of roles.

## Verification
Confirm no snapshot is public and EBS default encryption is enabled account-wide.
