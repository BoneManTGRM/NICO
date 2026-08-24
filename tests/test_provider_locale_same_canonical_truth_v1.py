from __future__ import annotations

import base64
import hashlib
from copy import deepcopy

import pytest

from nico.comprehensive_report_spanish_artifacts_v51 import _localize_package
from nico.provider_locale_semantic_parity_v1 import (
    assert_locale_semantic_parity,
    locale_neutral_truth_sha256,
)


def _frozen_canonical(*, provider: str, repository: str) -> dict:
    return {
        "identity": {
            "provider": provider,
            "repository": repository,
            "commit_sha": "a" * 40,
            "run_id": "comprun_locale_pair",
            "report_language": "en-US",
        },
        "report_language": "en-US",
        "locale": "en-US",
        "assessment": {
            "report_language": "en-US",
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 93,
            "executive_summary": "Assessment complete as an automated draft.",
            "sections": [],
            "scanner_execution_records": [],
            "scope_boundaries": [],
        },
        "findings_register": [],
        "stage_summaries": [],
        "roadmap": [],
        "staffing_plan": [],
        "human_review_required": True,
        "human_approval_completed": False,
        "client_delivery_allowed": False,
    }


@pytest.mark.parametrize(
    ("provider", "repository"),
    (
        ("gitlab", "gitlab.com/group/repo"),
        ("bitbucket_cloud", "bitbucket.org/workspace/repo"),
        ("azure_devops", "dev.azure.com/org/project/_git/repo"),
    ),
)
def test_priority1_spanish_artifacts_render_from_same_frozen_locale_neutral_canonical_truth(
    provider: str,
    repository: str,
) -> None:
    english = _frozen_canonical(provider=provider, repository=repository)
    frozen_digest = locale_neutral_truth_sha256(english)
    result = {
        "report_package": {
            "json": deepcopy(english),
            "report_quality_contract": {},
        }
    }

    localized = _localize_package(result)
    package = localized["report_package"]
    spanish = package["json"]

    assert assert_locale_semantic_parity(english, spanish) == frozen_digest
    assert spanish["identity"]["provider"] == english["identity"]["provider"]
    assert spanish["identity"]["repository"] == english["identity"]["repository"]
    assert spanish["identity"]["commit_sha"] == english["identity"]["commit_sha"]
    assert spanish["identity"]["run_id"] == english["identity"]["run_id"]
    assert spanish["assessment"]["technical_score"] == 93
    assert spanish["assessment"]["canonical_evidence_adjusted_score"] == 93
    assert spanish["human_review_required"] is True
    assert spanish["human_approval_completed"] is False
    assert spanish["client_delivery_allowed"] is False

    assert package["report_language"] == "es-MX"
    assert package["locale"] == "es-MX"
    assert package["report_quality_contract"]["localized_client_artifacts_share_canonical_truth"] is True
    assert package["markdown_sha256"] == hashlib.sha256(package["markdown"].encode("utf-8")).hexdigest()
    assert package["html_sha256"] == hashlib.sha256(package["html"].encode("utf-8")).hexdigest()
    pdf = base64.b64decode(package["pdf_base64"])
    assert package["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert pdf.startswith(b"%PDF")


def test_locale_neutral_comparison_detects_score_or_identity_drift() -> None:
    english = _frozen_canonical(provider="gitlab", repository="gitlab.com/group/repo")
    spanish = deepcopy(english)
    spanish["report_language"] = "es-MX"
    spanish["locale"] = "es-MX"
    spanish["assessment"]["report_language"] = "es-MX"
    assert_locale_semantic_parity(english, spanish)

    spanish["assessment"]["technical_score"] = 92
    with pytest.raises(ValueError, match="locale_canonical_semantic_mismatch"):
        assert_locale_semantic_parity(english, spanish)
