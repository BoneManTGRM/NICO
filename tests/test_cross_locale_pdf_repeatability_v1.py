"""Real cross-locale PDF repeatability under one immutable input.

Production Mobile run 37141240867 correctly rejected different English bytes
for the same run/source proof. This diagnostic executes the real assembler;
it never weakens the byte, run, locale, truth or pending-review contracts.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import time
from copy import deepcopy

import pytest
from pypdf import PdfReader

from nico import comprehensive_same_run_locale_report_v1 as locale_report
from nico.comprehensive_report_review_integrity_v1 import (
    install_comprehensive_report_review_integrity_v1,
)
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from tests.test_v2_premium_report_renderer import _package


def _fixed_status(source_language: str) -> dict:
    install_comprehensive_report_review_integrity_v1()
    source = rebuild_client_artifacts(_package(source_language))
    canonical = deepcopy(source["json"])
    reports = deepcopy(source)
    reports["report_id"] = "comprehensive_report_locale_repeatability"
    reports["canonical_truth_sha256"] = locale_report.canonical_sha256(canonical)
    return {
        "run_id": canonical["identity"]["run_id"],
        "repository": canonical["identity"]["repository"],
        "commit_sha": canonical["identity"]["commit_sha"],
        "evidence_ledger_id": canonical["identity"]["evidence_ledger_id"],
        "report_language": source_language,
        "terminal": True,
        "reports": reports,
    }


def _pdf_observation(status: dict, target_language: str) -> dict:
    install_comprehensive_report_review_integrity_v1()
    before = deepcopy(status)
    response = locale_report.build_same_run_locale_pdf_response(status, target_language)
    pdf = response.body
    observed = hashlib.sha256(pdf).hexdigest()
    assert status == before, "The read-only artifact path mutated retained input"
    assert pdf.startswith(b"%PDF-")
    assert response.status_code == 200
    assert response.headers["x-nico-artifact-sha256"] == observed
    assert response.headers["x-nico-pdf-sha256"] == observed
    assert response.headers["x-nico-run-id"] == status["run_id"]
    assert response.headers["x-nico-commit-sha"] == status["commit_sha"]
    assert response.headers["x-nico-report-language"] == target_language
    assert response.headers["x-nico-canonical-truth-sha256"] == status["reports"]["canonical_truth_sha256"]
    assert response.headers["x-nico-assessment-rerun"] == "false"
    assert response.headers["x-nico-approval-status"] == "pending_human_approval"
    assert response.headers["x-nico-client-delivery-allowed"] == "false"
    assert response.headers["x-nico-delivery-status"] == "blocked_pending_human_approval"
    reader = PdfReader(io.BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return {
        "pdf_sha256": observed,
        "bytes": len(pdf),
        "pages": len(reader.pages),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "metadata": {str(k): str(v) for k, v in (reader.metadata or {}).items()},
        "document_id": str(reader.trailer.get("/ID")),
        "canonical_truth_sha256": status["reports"]["canonical_truth_sha256"],
        "report_language": target_language,
    }


def _fresh_process_observation(status: dict, target_language: str) -> dict:
    script = (
        "import json,sys;"
        "from tests.test_cross_locale_pdf_repeatability_v1 import _pdf_observation;"
        "s,t=json.load(sys.stdin);"
        "print('NICO_LOCALE_PDF_OBSERVATION='+json.dumps(_pdf_observation(s,t),sort_keys=True))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps([status, target_language]),
        text=True,
        capture_output=True,
        timeout=180,
        env={**os.environ, "PYTHONHASHSEED": "0"},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    lines = [
        line.removeprefix("NICO_LOCALE_PDF_OBSERVATION=")
        for line in result.stdout.splitlines()
        if line.startswith("NICO_LOCALE_PDF_OBSERVATION=")
    ]
    assert len(lines) == 1, "A genuine nonempty producer observation is required"
    return json.loads(lines[0])


@pytest.mark.parametrize("source_language,target_language", (("en", "es-MX"), ("es-MX", "en")))
@pytest.mark.parametrize("mode", ("warm", "fresh_process"))
def test_same_frozen_input_keeps_cross_locale_pdf_bytes(source_language, target_language, mode):
    status = _fixed_status(source_language)
    before = deepcopy(status)
    if mode == "warm":
        first = _pdf_observation(status, target_language)
        time.sleep(1.05)  # Challenge accidental wall-clock metadata reuse.
        second = _pdf_observation(status, target_language)
    else:
        first = _fresh_process_observation(status, target_language)
        time.sleep(1.05)
        second = _fresh_process_observation(status, target_language)
    assert status == before
    assert first["pdf_sha256"] == second["pdf_sha256"], json.dumps(
        {"first": first, "second": second, "mode": mode}, sort_keys=True
    )
