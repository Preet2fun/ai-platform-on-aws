"""Tests for metadata inference."""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.metadata import infer_service, infer_topic, build_metadata


def test_infer_service():
    assert infer_service("Configure your S3 bucket policy") == "s3"
    assert infer_service("IAM roles and policies") == "iam"
    assert infer_service("nothing relevant here") is None


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
