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
    "s3", "iam", "ec2", "ebs", "vpc", "lambda", "rds", "kms", "cloudtrail", "cloudwatch",
    "guardduty", "security hub", "securityhub", "cognito", "api gateway", "apigateway",
    "eks", "ecs", "dynamodb", "sns", "sqs", "secrets manager", "config", "waf",
    "route 53", "route53",
]

TOPIC_HINTS = {
    "configuration": ["configure", "configuration", "setup", "enable", "harden", "settings"],
    "attack": ["attack", "exploit", "vulnerab", "breach", "compromise", "exposure", "ssrf",
               "privilege escalation", "exfiltrat"],
    "prevention": ["prevent", "mitigat", "remediat", "protect", "defen", "block", "best practice"],
}


# Aliases that map to a canonical service key (so "route 53"/"route53" -> route53, etc.).
_SERVICE_ALIASES = {
    "security hub": "securityhub",
    "api gateway": "apigateway",
    "route 53": "route53",
    "secrets manager": "secretsmanager",
}


def _canonical(svc: str) -> str:
    return _SERVICE_ALIASES.get(svc, svc.replace(" ", "_"))


def _service_in_source(source: str) -> str | None:
    """The service that appears EARLIEST in the source filename/title, if any.

    The doc's own name is the authoritative subject signal: `rds-iam-auth.md` is about RDS
    (RDS comes first) even though it mentions IAM heavily. Returns the canonical service.
    """
    if not source:
        return None
    src = source.lower().replace("-", " ").replace("_", " ")
    best_pos, best_svc = None, None
    for svc in AWS_SERVICES:
        m = re.search(rf"\b{re.escape(svc)}\b", src)
        if m and (best_pos is None or m.start() < best_pos):
            best_pos, best_svc = m.start(), svc
    return _canonical(best_svc) if best_svc else None


def infer_service(text: str, source: str = "") -> str | None:
    """Infer the primary AWS service for a chunk.

    Two-tier, fixing the earlier bug where nearly every doc was tagged `iam` (it was early in
    the list and every security doc mentions IAM):
      1. **Filename/title first** — if a service name appears in `source`, use the one that
         appears earliest there (the doc's subject). Most reliable signal.
      2. **Body frequency fallback** — otherwise score by how often each service is mentioned
         in the text and pick the most-mentioned (not first-in-list).
    Returns the canonical service, or None if nothing matches.
    """
    from_src = _service_in_source(source)
    if from_src:
        return from_src

    low = text.lower()
    scores: dict[str, float] = {}
    for svc in AWS_SERVICES:
        hits = len(re.findall(rf"\b{re.escape(svc)}\b", low))
        if hits > 0:
            key = _canonical(svc)
            scores[key] = scores.get(key, 0) + hits
    if not scores:
        return None
    return max(scores, key=scores.get)


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
        "service": infer_service(text_sample, source=f"{source} {title or ''}"),
        "topic": infer_topic(text_sample),
        "version": version,
        "sensitivity": sensitivity,
    }
    if overrides:
        md.update({k: v for k, v in overrides.items() if v is not None})
    return md
