"""Metadata extraction for chunks.

Attaches structured attributes so retrieval can filter (query construction) and so access
control / freshness are enforceable. v1 infers a best-effort AWS `service` and question
`topic` from the text; these can be overridden by a per-document sidecar manifest.
"""

from __future__ import annotations

import re
from typing import Any

# Small starter map; expand as the corpus grows. Keys are lowercased service hints.
AWS_SERVICES = [
    "s3", "iam", "ec2", "vpc", "lambda", "rds", "kms", "cloudtrail", "cloudwatch",
    "guardduty", "security hub", "securityhub", "cognito", "api gateway", "eks", "ecs",
    "dynamodb", "sns", "sqs", "secrets manager", "config", "waf", "route 53", "route53",
]

TOPIC_HINTS = {
    "configuration": ["configure", "configuration", "setup", "enable", "harden", "settings"],
    "attack": ["attack", "exploit", "vulnerab", "breach", "compromise", "exposure", "ssrf",
               "privilege escalation", "exfiltrat"],
    "prevention": ["prevent", "mitigat", "remediat", "protect", "defen", "block", "best practice"],
}


def infer_service(text: str) -> str | None:
    low = text.lower()
    for svc in AWS_SERVICES:
        if re.search(rf"\b{re.escape(svc)}\b", low):
            return svc.replace(" ", "_")
    return None


def infer_topic(text: str) -> str | None:
    low = text.lower()
    scores = {t: sum(low.count(h) for h in hints) for t, hints in TOPIC_HINTS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def build_metadata(
    *,
    source: str,
    title: str | None = None,
    version: str | None = None,
    sensitivity: str = "public",
    text_sample: str = "",
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    md: dict[str, Any] = {
        "source": source,
        "title": title,
        "service": infer_service(text_sample),
        "topic": infer_topic(text_sample),
        "version": version,
        "sensitivity": sensitivity,
    }
    if overrides:
        md.update({k: v for k, v in overrides.items() if v is not None})
    return md
