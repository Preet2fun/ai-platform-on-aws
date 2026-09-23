# AWS KMS Key Policy and Encryption Security

## Secure configuration
AWS KMS keys are governed by a key policy plus optional IAM policies and grants. The key policy
is the primary access control. Scope it so only specific roles can use the key
(`kms:Encrypt`/`kms:Decrypt`) and a separate, small set of admins can manage it
(`kms:PutKeyPolicy`, `kms:ScheduleKeyDeletion`). Enable automatic annual key rotation for
customer-managed keys.

## How an attack happens
An overly broad key policy that grants `kms:*` to the whole account, or `Decrypt` to a wildcard
principal, lets any compromised principal decrypt protected data. Attackers also look for keys
whose policy allows them to add themselves via `kms:PutKeyPolicy`.

## Prevention
- Write least-privilege key policies; separate key usage from key administration.
- Never grant `kms:*` or `Decrypt` to `Principal: "*"` without tight conditions.
- Use `kms:ViaService` and `kms:EncryptionContext` conditions to constrain usage.
- Enable key rotation and CloudTrail logging of KMS API calls.
- Use grants for temporary, scoped delegation instead of broad policy changes.

## Verification
Review each CMK's policy for wildcard principals and confirm rotation + CloudTrail are enabled.
