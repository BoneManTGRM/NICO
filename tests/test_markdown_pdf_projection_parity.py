"""Copied pending Markdown must identify the bytes listed in its review PDF."""
import base64
from copy import deepcopy
import io

import pytest
from pypdf import PdfReader

from nico import comprehensive_same_run_locale_report_v1 as locale
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from tests.test_v2_premium_report_renderer import _package


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_regenerated_markdown_matches_the_pdf_manifest_byte_set(language):
    fixture = _package("en")
    fixture["json"]["report_id"] = "synthetic-projection-parity"
    source = rebuild_client_artifacts(fixture)
    canonical = source["json"]
    status = {
        **canonical["identity"], "reports": source, "terminal": True,
        "human_review_required": True, "human_review_completed": False,
        "client_delivery_allowed": False, "approval_status": "pending_human_approval",
        "_nico_force_pending_draft_artifact_regeneration": True,
    }
    before = deepcopy(status)
    copied = locale.build_same_run_locale_markdown_projection(status, language)
    rendered = locale.build_same_run_locale_report(status, language)
    pdf = PdfReader(io.BytesIO(base64.b64decode(rendered["report"]["pdf_base64"])))
    visible = "".join("".join(page.extract_text().split()) for page in pdf.pages)
    assert copied["report"]["markdown_sha256"] in visible
    assert copied["report"]["markdown"] == rendered["report"]["markdown"]
    assert copied["artifact_scope"] == "client-facing-same-run-projection"
    assert copied["localized_artifact_requires_new_approval"] is True
    assert copied["report"]["client_delivery_allowed"] is False
    assert copied["assessment_rerun"] is False
    assert status == before
