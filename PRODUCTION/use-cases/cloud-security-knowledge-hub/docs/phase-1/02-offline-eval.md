# Phase 1 · Stage B — Offline Evaluation (golden-set quality gate)

> **Offline eval** = fixed golden set + ground truth, run as a pre-release quality gate (not
> production traffic). Re-run on the **post-SRA corpus** (19 docs / 337 chunks) and compared to
> the Iteration-1 baseline. Config label: `phase1-post-sra`.

## B.1 — Golden set update
Added **4 SRA golden Q&A pairs** grounded in the actually-indexed SRA content (org-level S3
Block Public Access, shared-responsibility model, AWS Config rules, Audit Manager). Golden set:
**38 → 42 pairs** (17 configuration / 13 attack / 12 prevention), all `reviewed_by=human`.

## B.2 — Run
`offline/collect.py` (42 Qs against the live API) → `offline/score.py` (Bedrock LLM-as-judge) →
`results/phase1-post-sra.json`, emitted to CloudWatch `CSHub/Eval`.
- Collection: **41 answered, 1 "I don't know", 0 errors.**
- All 4 SRA questions **retrieved SRA chunks and produced correct, grounded answers** (verified
  from the collected records).

## B.3 — Results (read carefully — three layers)

### Raw aggregate (all 42) — **do not use as the headline**
| Metric | Raw (42) |
|---|---|
| Faithfulness | 0.828 |
| Answer relevancy | 0.891 |
| Context precision | 0.850 |
| Context recall | 0.856 |

The raw numbers are **depressed by a scorer artifact**: the 4 SRA questions scored 0.00 not
because the answers were bad, but because the offline scorer reconstructs context from **local
sample files** and the SRA PDF isn't one (it went straight to S3) → the judge saw empty context
→ 0.00. This is **FI-4**, a false negative in the scorer, not a quality failure.

### Corrected aggregate (37 non-SRA questions) — the comparable number
| Metric | Iteration-1 baseline (38 Qs) | Post-SRA (37 non-SRA Qs) | Δ |
|---|---|---|---|
| Faithfulness | 0.984 | 0.915 | −0.069 |
| Answer relevancy | 0.976 | 0.959 | −0.017 |
| Context precision | 0.940 | 0.932 | −0.008 |
| Context recall | 0.947 | 0.938 | −0.009 |
| p95 latency (ms) | 7,046 | 7,506 | +460 |

The small drop is driven almost entirely by **one genuine regression** (`iam-config-001`).
Excluding it (36 Qs), the corpus is still ~0.94 faithfulness / 0.99 relevancy / 0.96 precision
/ 0.96 recall — i.e. quality on the existing content held up.

### The genuine regression — `iam-config-001` (FI-5)
This question **passed at ~1.0 in Iteration-1** and now **returns "I don't have enough
information" (0.00)**. Cause: the SRA added **307 IAM-heavy chunks**, which crowd the top-6
dense retrieval for IAM queries and push out the specific `iam-least-privilege.md` chunk that
used to answer it. A real retrieval regression from corpus growth on a **dense-only, no-rerank**
baseline. This is the headline motivation for Phase 2 (hybrid + rerank + larger top-K).

## B.4 — Findings (in `FUTURE-IMPROVEMENTS.md`)
- **FI-4 (⏳):** offline scorer uses local-sample context → false 0.00 on S3-only docs. Fix:
  score against real retrieved context (API returns passages, or fetch from Aurora).
- **FI-5 (⏳, Phase 2):** IAM retrieval regressed after corpus growth → advanced RAG needed.

## B.5 — Gate verdict
Against `thresholds.json` floors (faith 0.80 / rel 0.75 / cp 0.70 / cr 0.70): the **corrected**
scores pass comfortably; the **raw** aggregate also passes the floors but is misleading. p95
latency (7,506ms) still exceeds the 6,000ms ceiling (unchanged Phase-1 characteristic).

## B.6 — What this stage proved
- Offline eval **works as a regression detector**: it caught a real IAM-retrieval regression
  and a real scorer limitation the moment the corpus changed — exactly its purpose.
- The new SRA content is **searchable and correctly answered** live (the 0.00s are a scoring
  artifact, corrected above).
- Honest headline: **corrected faithfulness 0.915 / relevancy 0.959 / precision 0.932 /
  recall 0.938** on the post-SRA corpus, with one identified regression feeding Phase 2.
