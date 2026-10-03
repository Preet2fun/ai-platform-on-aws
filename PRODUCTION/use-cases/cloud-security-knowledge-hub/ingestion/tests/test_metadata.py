"""Tests for metadata inference."""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.metadata import (
    infer_service, infer_topic, build_metadata, infer_chunk_service, build_chunk_metadata,
)


def test_infer_service():
    assert infer_service("Configure your S3 bucket policy") == "s3"
    assert infer_service("IAM roles and policies") == "iam"
    assert infer_service("nothing relevant here") is None


def test_infer_service_filename_wins_over_incidental_iam_mention():
    # Regression: a DynamoDB doc that mentions IAM should tag dynamodb, not iam.
    text = ("DynamoDB encrypts tables. Control access with IAM policies scoped to table ARNs; "
            "grant dynamodb:GetItem via IAM. IAM condition keys enable row-level access.")
    assert infer_service(text, source="dynamodb-security.md") == "dynamodb"


def test_infer_service_earliest_in_filename_wins():
    # rds-iam-auth.md is about RDS (RDS appears first in the name), despite heavy IAM text.
    text = "Enable IAM database authentication. Grant iam rds-db:connect. IAM tokens..."
    assert infer_service(text, source="rds-iam-auth.md") == "rds"


def test_infer_service_body_frequency_fallback_when_no_filename_hint():
    # No service in the source name -> pick the most-mentioned in the body (not first-in-list).
    text = "lambda lambda lambda function. iam is mentioned once."
    assert infer_service(text, source="notes.md") == "lambda"


def test_infer_service_alias_canonicalization():
    assert infer_service("configure the API Gateway", source="apigateway-security.md") == "apigateway"
    assert infer_service("protect Route 53 zones", source="route53-dns-security.md") == "route53"


def test_infer_topic():
    assert infer_topic("how to configure and enable this securely") == "configuration"
    assert infer_topic("this exploit and vulnerability leads to compromise") == "attack"
    assert infer_topic("how to prevent and mitigate the risk") == "prevention"


def test_build_metadata_defaults_and_overrides():
    md = build_metadata(source="s3-guide.pdf", text_sample="Configure the S3 bucket to prevent public exposure")
    assert md["source"] == "s3-guide.pdf"
    assert md["service"] == "s3"
    assert md["sensitivity"] == "public"
    assert md["topic"] in {"configuration", "prevention"}

    md2 = build_metadata(source="x", text_sample="", overrides={"sensitivity": "internal", "service": "iam"})
    assert md2["sensitivity"] == "internal"
    assert md2["service"] == "iam"


# ---- FI-3: per-chunk service classification ----

def test_infer_chunk_service_uses_body_not_filename():
    # A chunk about S3 inside a doc named for the SRA (no service in name) -> s3, not a doc tag.
    text = "Enable S3 Block Public Access on every bucket and use SSE-KMS default encryption."
    assert infer_chunk_service(text, source="aws-security-reference-architecture-v4.pdf") == "s3"


def test_infer_chunk_service_body_wins_over_filename_service():
    # Even when the filename names a service, a chunk that clearly discusses another wins.
    text = "This section is entirely about Amazon EKS pod identity and IRSA for EKS workloads eks."
    assert infer_chunk_service(text, source="iam-least-privilege.md") == "eks"


def test_infer_chunk_service_falls_back_to_filename_when_body_empty():
    # A heading-only / serviceless chunk falls back to the filename hint.
    assert infer_chunk_service("Overview and background.", source="kms-key-security.md") == "kms"
    assert infer_chunk_service("Overview.", source="notes.md") is None


def test_build_chunk_metadata_per_chunk_service_not_doc_clobber():
    # THE FI-3 REGRESSION: a multi-service doc (doc-level service=iam) must NOT stamp iam on an
    # S3 chunk. The chunk's own text must win; doc-level fields are inherited.
    doc_md = {"source": "aws-security-reference-architecture-v4.pdf", "title": "SRA",
              "service": "iam", "topic": "prevention", "version": "v4", "sensitivity": "public"}
    s3_chunk = "S3 Block Public Access and bucket policies prevent public S3 exposure."
    cm = build_chunk_metadata(chunk_text=s3_chunk, doc_metadata=doc_md)
    assert cm["service"] == "s3"                      # per-chunk wins, NOT doc-level iam
    assert cm["source"] == doc_md["source"]           # doc-level fields inherited
    assert cm["version"] == "v4" and cm["sensitivity"] == "public"


def test_build_chunk_metadata_falls_back_to_doc_service_when_chunk_ambiguous():
    doc_md = {"source": "iam-least-privilege.md", "service": "iam", "sensitivity": "public"}
    cm = build_chunk_metadata(chunk_text="Introduction and overview.", doc_metadata=doc_md)
    assert cm["service"] == "iam"                     # nothing in chunk body -> doc fallback
