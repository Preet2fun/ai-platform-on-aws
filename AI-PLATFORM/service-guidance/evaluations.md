# Service Guidance — Evaluations

> How we measure and maintain agent quality. Source: skill `services/evaluations/`.

## Standard
- Instrument agents for trace collection (ties into Observability).
- **Evaluators:** built-in (e.g. `Builtin.Helpfulness`) + **custom** for domain quality:
  RCA correctness, triage accuracy, false-positive rate for security findings.
- **Online evaluation** with sampling on production sessions; investigate low scores.
- Feed eval outcomes into the **episodic memory** loop so quality improves over time.

## Best practices
- [ ] Evaluator definitions per PRODUCTION use case (RCA / SRE / Security)
- [ ] Scoring thresholds + review workflow for low-scoring incident sessions
- [ ] Offline/regression eval set for pre-deploy testing

## POC gaps addressed
- No evaluation today. Establish evaluators + online eval as part of every PRODUCTION rollout.
