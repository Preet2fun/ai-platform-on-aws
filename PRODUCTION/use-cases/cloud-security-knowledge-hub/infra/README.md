# Infrastructure — P0 Foundation (raw CloudFormation)

The deployable foundation for the Cloud Security Knowledge Hub. Raw CloudFormation, deployed
as separate stacks linked by cross-stack **Exports/ImportValue**, in dependency order.

> Account `001961766007` · region `us-east-1` · profile `agentcore` · budget-conscious.

## Stacks (deploy order)

| # | Stack | Template | What it creates | Depends on |
|---|---|---|---|---|
| 1 | `cshub-<env>-network` | `00-network.yaml` | VPC, 2 public + 2 private subnets, 1 NAT, SGs, VPC endpoints (S3 gw + Bedrock/Secrets/Logs interface) | — |
| 2 | `cshub-<env>-data` | `01-data-stores.yaml` | KMS CMK, 3 S3 buckets (raw/processed/artifacts), DB secret, Aurora Serverless v2 cluster+instance | network |
| 3 | `cshub-<env>-pgvector` | `02-pgvector-bootstrap.yaml` | Lambda custom resource: enables `vector` ext + creates hybrid schema (dense + full-text) | data |
| 4 | `cshub-<env>-cicd` | `06-cicd.yaml` | GitHub OIDC provider + GitHub Actions deploy role | — |

## Deploy

```bash
# fill in params/dev.json first (esp. GitHubOrg)
AWS_PROFILE=agentcore AWS_REGION=us-east-1 ./deploy.sh dev
```
`deploy.sh` runs all four stacks in order (idempotent; uses `aws cloudformation deploy`).
All templates pass `aws cloudformation validate-template`.

Deploy a single stack manually, e.g.:
```bash
aws cloudformation deploy --stack-name cshub-dev-network \
  --template-file 00-network.yaml --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides ProjectName=cshub EnvName=dev VpcCidr=10.20.0.0/16
```

## Parameters
Edit `params/dev.json`. Key knobs:
- `MinAcu` / `MaxAcu` — Aurora Serverless v2 capacity (**MinAcu is the main cost lever**; keep at `0.5`).
- `EmbeddingDim` — `1024` for Titan Text Embeddings v2.
- `GitHubOrg` / `GitHubRepo` / `GitHubRef` — scope the CI/CD deploy role. **Set `GitHubOrg`.**
- `CreateOidcProvider` — set `false` if the GitHub OIDC provider already exists in the account.

## Important build notes (before this actually runs)

1. **pgvector Lambda needs a Postgres driver.** `02-pgvector-bootstrap.yaml` ships an inline
   handler that documents the exact bootstrap SQL but does **not** connect (inline code can't
   include `psycopg`). In CI, package the Lambda with a `psycopg`/`pg8000` layer or zip and
   point the function at it; the DDL to run is in the template. Until then the custom resource
   succeeds as a no-op placeholder (so the stack completes) — swap to the packaged artifact to
   actually create the schema.
2. **Aurora engine version.** `EngineVersion` defaults to `16.4`; confirm a version available
   in `us-east-1` that supports Serverless v2 **and** pgvector before deploy
   (`aws rds describe-db-engine-versions --engine aurora-postgresql`).
3. **CI/CD role is broad for bootstrap.** `06-cicd.yaml` grants `PowerUserAccess` + IAM for
   convenience. **Tighten to least-privilege** (only the services this stack set touches)
   before production, per the AI-PLATFORM guardrails standard.
4. **S3 buckets are `Retain`** on delete and **Aurora is `Snapshot`** — deleting a stack won't
   destroy data. Clean up manually if you truly want them gone.

## Exports (consumed by later phases)
`VpcId`, `PublicSubnetIds`, `PrivateSubnetIds`, `LambdaSgId`, `AuroraSgId`, `KmsKeyArn`,
`RawBucket`, `ProcessedBucket`, `ArtifactsBucket`, `DbSecretArn`, `DbEndpoint`, `DbName`,
`DeployRoleArn`. P1 (ingestion) and P2 (query service) import these.

## What's next (P1)
Ingestion pipeline: `02-ingestion.yaml` (Step Functions + Lambdas + Fargate + EventBridge +
Textract) writing into the Aurora schema this stack bootstraps.
