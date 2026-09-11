# Golden Dataset Schema

The golden set is the measurement backbone (see `AI-SDLC-AND-EVALS.md §2`). One JSONL file,
one example per line, versioned in git so eval runs are comparable across releases.

## Fields (per line)

| Field | Required | Description |
|---|---|---|
| `id` | ✅ | Stable unique id (e.g. `s3-config-001`) |
| `question` | ✅ | The user question |
| `question_type` | ✅ | One of `configuration`, `attack`, `prevention` |
| `service` | ✅ | Primary AWS service (e.g. `s3`, `iam`, `ec2`) |
| `ground_truth` | ✅ | The ideal, correct answer (for correctness/RAGAS) |
| `expected_source_ids` | ⬜ | doc/chunk ids that should be retrieved (for context recall) |
| `notes` | ⬜ | Reviewer notes / edge-case flags |
| `reviewed_by` | ⬜ | Human reviewer (generated pairs must be reviewed before use) |

## Example line
```json
{"id":"s3-config-001","question":"How do I securely configure an S3 bucket to prevent public access?","question_type":"configuration","service":"s3","ground_truth":"Enable S3 Block Public Access at the account and bucket level, keep ACLs disabled (bucket owner enforced), use bucket policies that deny public principals, enable default encryption, and turn on access logging and versioning.","expected_source_ids":["s3-security-guide::0003"],"reviewed_by":"human"}
```

## Rules
- Every generated pair MUST be human-reviewed (`reviewed_by` set) before it counts toward the gate.
- Cover all three `question_type`s and a spread of services.
- Keep `ground_truth` grounded in the corpus (don't invent facts the corpus lacks).
- Target ~100–200 reviewed pairs for v1; grow from real user queries over time.
