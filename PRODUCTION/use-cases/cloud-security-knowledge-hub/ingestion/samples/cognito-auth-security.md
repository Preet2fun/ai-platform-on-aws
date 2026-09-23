# Amazon Cognito Authentication Security

## Secure configuration
Configure Cognito user pools with a strong password policy, email or phone verification, and
MFA (prefer TOTP or WebAuthn over SMS). For app clients, use the authorization-code grant with
PKCE and do not generate a client secret for public SPAs. Set exact callback and logout URLs;
never use wildcards. Keep access-token lifetimes short and rely on refresh-token rotation.

## How an attack happens
Weak or missing MFA enables credential-stuffing and account takeover. Overly broad callback
URLs or the implicit grant can leak tokens. A public client configured with a secret, or tokens
stored in localStorage, expand the attack surface for XSS-based theft.

## Prevention
- Require MFA; prefer TOTP/WebAuthn. Enable advanced security (compromised-credentials check).
- Use authorization-code + PKCE for SPAs; avoid the implicit grant.
- Pin exact callback/logout URLs; disable unused OAuth flows and scopes.
- Store tokens in memory or sessionStorage, not localStorage; set short token TTLs.
- Monitor sign-in events and enable account-takeover protection.

## Verification
Confirm MFA is enforced, the app client uses code+PKCE with exact URLs, and advanced security
is enabled.
