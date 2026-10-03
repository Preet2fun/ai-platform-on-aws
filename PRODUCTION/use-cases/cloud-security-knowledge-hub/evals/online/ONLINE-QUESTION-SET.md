# Frozen Online Question Set — Phase-1-vs-Phase-2 head-to-head

> **Purpose:** a single **fixed** list asked **identically** in the Phase-1 and Phase-2 online
> runs so the online A/B is fair (same inputs, only the query-time flags differ). Ask these in
> the deployed UI (`https://d1s8aphl5ns4nb.cloudfront.net`), in order, once per phase.
>
> **This is the actual set run in Phase-1** (`phase1-final-online`, 2026-09-28). Phase-2 must
> reuse **exactly these 13** for a fair comparison.
>
> **How it's scored:** each question emits a `CSHUB_QA` log line + an FI-6 trace span; after a
> phase's run, `evals/online/score_online.py --from-traces --minutes <N> --config <phaseX-final-online>`
> pulls that window and scores it (faithfulness + relevancy via LLM-judge, plus behavioural
> proxies). No ground truth online — an honest "I don't have that" to an out-of-scope question
> scores high on faithfulness (the 3 OOC questions are here to exercise that + CRAG in Phase-2).
>
> **Rules for a fair run:** ask all 13, in order, same wording both phases; don't ask other
> questions inside the scored window; note the UTC start time.

## The 13 questions (as run in Phase-1)

**In-corpus (Q1–Q10)** — expect a grounded, cited answer:
1. How should I configure AWS WAF to protect a public-facing web application from SQL injection, XSS, bots, and common web attacks?
2. Which AWS security services should I enable to detect suspicious activities, compromised credentials, cryptocurrency mining, and unusual API calls in my AWS environment?
3. How can I configure Amazon GuardDuty, and what actions should be taken when GuardDuty detects a high-severity finding?
4. How can AWS Shield Advanced and AWS WAF work together to protect my SaaS application against DDoS attacks?
5. How should I configure AWS IAM to follow least-privilege principles and prevent privilege-escalation attacks?
6. How can I detect and prevent accidental public exposure of sensitive data stored in Amazon S3 buckets?
7. Which AWS services and configurations can help detect if an attacker has stolen an IAM user's access key and is using it from an unusual location or IP address?
8. How should AWS Security Hub be configured to centrally monitor security findings from GuardDuty, Inspector, Macie, IAM Access Analyzer, and other AWS security services?
9. How can Amazon Inspector be used to continuously identify vulnerabilities in EC2 instances, ECR container images, and AWS Lambda functions, and how should critical findings be prioritized for remediation?
10. Assume an attacker compromises an EC2 instance in a private subnet. Which AWS security controls can detect the compromise, prevent lateral movement, restrict access to other workloads, and help investigate the incident?

**Out-of-corpus (Q11–Q13)** — expect an honest refusal ("I don't have that information"); these exercise CRAG in Phase-2:
11. what are the diffrnet WAF option avaiable in Azure WAF ?
12. Does GCP has any security rleted to encryption ?
13. what is distance between texas and NYC ?

## What we compare afterward (per question, Phase-1 vs Phase-2)
- **Answered vs IDK** — especially the 3 OOC (Q11–Q13, which should stay IDK).
- **Citations** — did Phase-2 cite the right chunks (esp. multi-service questions, tests FI-3 filter)?
- **Faithfulness / relevancy** (LLM-judge means).
- **Latency** — Phase-2 will be slower (rerank + CRAG + query-transform + CoN); quantify the cost.
- **Deflection rate** — Q11–Q13 should deflect (correct); any in-corpus deflection (Q1–Q10) is a gap.

> Config labels: Phase-1 → `Config=phase1-final-online`; Phase-2 → `phase2-final-online`
> (CloudWatch namespace `CSHub/OnlineEval`).
