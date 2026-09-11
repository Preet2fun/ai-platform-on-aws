# Cost Model & Reuse Analysis — Cloud Security Knowledge Hub

> Target: **~$300/month**, single region `us-east-1`, ~20 users, low/bursty traffic.
> **All figures are planning estimates — verify against the AWS Pricing Calculator at build
> time.** Pricing changes; treat these as directional, not quotes.

---

## 1. Cost drivers (biggest levers first)

1. **Aurora Serverless v2 minimum ACU** — the largest always-on cost. Keep min ACU low
   (0.5) and let it scale up only under load. This single setting dominates the monthly bill.
2. **Claude Sonnet generation tokens** — scales with query volume × context size. At 20 users
   this is modest, but long contexts (many retrieved chunks) inflate it — another reason
   re-ranking (fewer, better chunks) helps cost, not just quality.
3. **Everything else** (Lambda, API GW, Step Functions, S3, CloudFront, WAF) is small at this scale.

---

## 2. Monthly estimate (steady state)

| Service | Assumption | Est. $/mo |
|---|---|---|
| **Aurora Serverless v2** | min 0.5 ACU, scaling to ~1–2 ACU occasionally | **$45–90** |
| **Bedrock — Claude Sonnet** | ~20 users, light daily use, re-ranked (small) contexts | **$30–90** |
| **Bedrock — Titan embeddings** | query embeds + periodic re-index | **$2–10** |
| **Bedrock — Cohere Rerank** (Phase 2) | top-K rerank per query | **$5–15** |
| **Bedrock — Guardrails** | per-request input/output checks | **$5–15** |
| **AWS Lambda + API Gateway** | query service, low volume | **$3–10** |
| **Step Functions + Fargate (ingestion)** | bursty, only during ingestion runs | **$5–25** |
| **S3 + CloudFront + WAF** | small corpus + static UI + edge | **$15–35** |
| **CloudWatch + X-Ray + Secrets + KMS** | dashboards, logs, tracing, keys | **$15–30** |
| **Textract** | one-time-ish per PDF batch (usage-based) | **$0–15** |
| **Total (steady state)** | | **≈ $130–260/mo** |

Headroom under the **$300** ceiling. Ingestion cost is spiky (only when indexing); steady-state
is dominated by Aurora + Claude.

> Excludes free-tier offsets and one-time setup. Video (Transcribe) is deferred and priced per
> minute of audio when added.

---

## 3. Cost controls (design-level)

- **Aurora:** min 0.5 ACU; auto-pause not available on Serverless v2, so keep min low. Consider
  pausing dev environments. Right-size max ACU to observed load.
- **Context size discipline:** re-ranking + Chain-of-Note reduce chunks sent to Claude → fewer
  input tokens → lower cost (quality and cost aligned).
- **Caching:** cache embeddings of repeated queries; CloudFront caches the static UI.
- **Lambda over Fargate** for the online path (scale-to-zero) — no idle compute.
- **Ingestion on Fargate** only during runs; scale-to-zero between.
- **Bounded log retention** on CloudWatch (e.g. 30–90 days) to avoid unbounded storage cost.
- **Budgets + alarms:** an AWS Budget at $300 with alerts at 50/80/100%.

---

## 4. Reuse vs. new (account `001961766007`)

### Reuse — account-level / shared only
| Item | Reuse? | Note |
|---|---|---|
| Bedrock model access (Claude, Titan, Cohere) | ✅ | Already enabled (71 inference profiles) |
| CloudTrail (org multi-region trail) | ✅ | Audit coverage already present |
| KMS / AWS Config / GuardDuty account settings | ✅ | Account-wide posture |
| IAM account (new scoped roles created within) | ✅ (account) | New least-privilege roles per component |

### Create new — all Hub application resources
| Item | New? | Why |
|---|---|---|
| **VPC** | ✅ dedicated | Isolate the public customer-facing Hub from the internal MSP POC (blast radius, security). Small cost. |
| S3 buckets (raw, processed, artifacts, UI) | ✅ | Hub-owned data |
| Aurora Serverless v2 + pgvector | ✅ | The knowledge store |
| Step Functions / Lambdas / Fargate | ✅ | Ingestion + query compute |
| API Gateway (HTTP) | ✅ | Public query endpoint |
| **Cognito user pool** | ✅ new | Separate customer identity from the POC's internal pool |
| CloudFront + WAF | ✅ | Edge + public protection |
| Secrets, dashboards, alarms | ✅ | Hub-scoped |

### Do NOT reuse
- The MSP POC's **AgentCore runtimes, gateway, and Cognito pool** — different system, users,
  and lifecycle. Reusing them would couple a customer-facing product to an internal experiment.

### VPC decision detail
- **Recommended: dedicated VPC.** Reasons: the Hub is **public/customer-facing** while the POC
  is internal; separate VPCs give clean network isolation, independent security groups, and no
  risk of one system's changes affecting the other. Cost delta is minimal (NAT is the main
  cost — use a single NAT or VPC endpoints to keep it low; Aurora + Lambda can use VPC
  endpoints for Bedrock/S3 to reduce NAT egress).
- **Alternative:** reuse `dev-vpc` private subnets to save the NAT cost. Acceptable for dev,
  but I recommend isolation for a production customer-facing system.

---

## 5. Scale-up path (when you outgrow v1)

| Trigger | Change | Cost impact |
|---|---|---|
| Traffic ↑ / cold-start UX issues | Lambda → Fargate (or Lambda provisioned concurrency) | +compute, smoother latency |
| Corpus ↑ / need stronger hybrid | Aurora pgvector → OpenSearch Serverless | +$350+/mo (only when justified) |
| Global users / HA | Multi-region (Aurora Global, CloudFront already global) | significant; defer until needed |
| Video content | Add Transcribe ingestion branch | usage-based per audio-minute |

The v1 design deliberately fits ~$300; each scale lever is opt-in and measured before adopting.
