# UI (P4) — static chat frontend + CloudFront edge

A minimal, build-free chat SPA for the Cloud Security Knowledge Hub. Vanilla HTML/CSS/JS —
no framework, no bundler. Served privately from S3 via CloudFront (see
`infra/04-edge-ui.yaml`).

## What it does
- **Sign in** via Cognito Hosted UI (OAuth2 authorization-code + **PKCE**, no client secret).
- **Ask** a question → `POST /query` with the Cognito `id_token` as the `Authorization` header.
- **Render** the grounded answer, its **citations** (source per `[n]`), and a passages/latency
  meta line. Handles the "I don't have enough information" and blocked-by-guardrail states.

## Files
```
ui/
├── index.html          # markup
├── app.js              # auth (PKCE) + query + rendering (build-free)
├── styles.css          # styling
├── config.js.template  # per-env public config (copy to config.js, fill from CFN outputs)
└── README.md
```

## Configure (from CloudFormation outputs)
1. Create a **Cognito Hosted UI domain** on the user pool (P2's `UserPool`) — e.g.
   `cshub-dev`. Add the CloudFront URL as an **allowed callback + logout URL** on the
   `UserPoolClient` (update P2's placeholder `https://localhost/...`).
2. Copy `config.js.template` → `config.js` and fill:
   - `userPoolId`, `userPoolClientId`, `apiEndpoint` — from `03-query-service.yaml` outputs
   - `cognitoDomain` — the Hosted UI domain URL
   - `redirectUri` — the CloudFront URL from `04-edge-ui.yaml` (`UiDomain`)

## Build / upload flow (CI, later)
```bash
# 1) render config.js from stack outputs (example)
#    (script reads outputs and substitutes the REPLACE_* placeholders)
# 2) sync static assets to the private site bucket
aws s3 sync ui/ "s3://$(aws cloudformation describe-stacks \
  --stack-name cshub-dev-edge-ui --query \
  'Stacks[0].Outputs[?ExportName==`cshub-dev-UiBucket`].OutputValue' --output text)/" \
  --exclude "config.js.template" --exclude "README.md"
# 3) invalidate CloudFront
aws cloudfront create-invalidation --distribution-id <UiDistributionId> --paths "/*"
```

## Tighten before prod
- **CORS:** P2's API currently allows `AllowOrigins: *` — restrict to the CloudFront domain.
- **Cognito callback/logout URLs:** replace the `https://localhost/...` placeholders with the
  real CloudFront (or custom-domain) URLs.
- **Custom domain + ACM cert:** `04-edge-ui.yaml` uses the default CloudFront cert; add an ACM
  cert + `Aliases` for a branded domain.
- **CSP:** add a Content-Security-Policy header (response-headers policy) once the exact
  Cognito/API origins are fixed.
- **WAF** already fronts the API (P2); consider a WAF on CloudFront too for the UI.

## Notes
- **Not deployed.** Template validated (`aws cloudformation validate-template`); UI is static
  assets. `app.js` passes `node --check`.
- All config values here are **public client values** (Cognito ids, API URL) — safe in the
  browser; no secrets.
- The SPA error routing (403/404 → index.html) makes CloudFront serve the app for any path.
