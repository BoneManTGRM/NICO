from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from pathlib import Path

import pytest

from nico.comprehensive_report_package import _canonical_hash
from nico.comprehensive_same_run_locale_report_v1 import (
    build_same_run_locale_pdf_response,
    build_same_run_locale_report,
)


def _historical_removed_field_status() -> tuple[dict, bytes]:
    original = {
        "service_id": "comprehensive",
        "identity": {
            "run_id": "comprun_historical_frozen_1",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "9" * 40,
            "evidence_ledger_id": "ledger_historical_frozen_1",
            "report_language": "en",
        },
        "report_language": "en",
        "assessment": {
            "report_language": "en",
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 93,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "stage_summaries": [],
        "phase5_removed_after_hash": {"legacy": True},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    expected_truth = _canonical_hash(original)
    persisted = deepcopy(original)
    persisted.pop("phase5_removed_after_hash")
    assert _canonical_hash(persisted) != expected_truth

    pdf_bytes = b"%PDF-1.4\n% historical immutable review artifact\n"
    status = {
        "run_id": original["identity"]["run_id"],
        "repository": original["identity"]["repository"],
        "commit_sha": original["identity"]["commit_sha"],
        "evidence_ledger_id": original["identity"]["evidence_ledger_id"],
        "report_language": "en",
        "terminal": True,
        "integrity_sha256": "run-integrity",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "reports": {
            "report_id": "comprehensive_report_historical_frozen_1",
            "canonical_truth_sha256": expected_truth,
            "json": persisted,
            "markdown": "# historical frozen report",
            "html": "<article>historical frozen report</article>",
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        },
    }
    return status, pdf_bytes


def test_source_language_pdf_fails_closed_when_old_json_cannot_prove_asserted_hash() -> None:
    status, _ = _historical_removed_field_status()

    # The canonical projection correctly remains blocked because the missing historical
    # field cannot be guessed or reconstructed from the persisted JSON.
    with pytest.raises(ValueError, match="canonical_truth_hash_mismatch"):
        build_same_run_locale_report(status, "en")

    # Current-release responses may not assert a canonical truth digest that the
    # persisted JSON cannot reproduce, even when historical PDF bytes still exist.
    with pytest.raises(ValueError, match="canonical_truth_hash_mismatch"):
        build_same_run_locale_pdf_response(status, "en")


def test_historical_cross_language_projection_still_fails_closed_on_unknown_hash_drift() -> None:
    status, _ = _historical_removed_field_status()

    with pytest.raises(ValueError, match="canonical_truth_hash_mismatch"):
        build_same_run_locale_pdf_response(status, "es-MX")


def test_frozen_source_pdf_recovery_rejects_run_identity_mismatch() -> None:
    status, _ = _historical_removed_field_status()
    status["run_id"] = "comprun_wrong_identity"

    with pytest.raises(ValueError, match="status_canonical_run_id_mismatch"):
        build_same_run_locale_pdf_response(status, "en")


def test_frozen_source_pdf_recovery_rejects_stored_pdf_hash_mismatch() -> None:
    status, _ = _historical_removed_field_status()
    status["reports"]["pdf_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="source_report_pdf_hash_mismatch"):
        build_same_run_locale_pdf_response(status, "en")


def test_isolated_final_report_worker_binds_hash_after_worker_local_report_wrappers() -> None:
    source = Path("nico/api/final_report_worker_bootstrap.py").read_text(encoding="utf-8")

    cache_install = "install_comprehensive_spanish_final_report_runtime_cache_v94()"
    hash_install = "CANONICAL_TRUTH_HASH_COMPAT = install_canonical_truth_hash_compat()"
    assert cache_install in source
    assert hash_install in source
    assert source.index(cache_install) < source.index(hash_install)
    assert '"canonical_truth_hash_sync_bound": True' in source
    assert 'CANONICAL_TRUTH_HASH_COMPAT.get("builder_hash_sync_bound") is not True' in source
