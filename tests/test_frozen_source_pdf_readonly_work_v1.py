from __future__ import annotations

import base64
import hashlib
import io
from collections import UserDict
from collections.abc import Mapping as RealMapping
from copy import deepcopy

import pytest
from reportlab.pdfgen import canvas

from nico import comprehensive_commercial_ship_projection_v3 as commercial
from nico import comprehensive_same_run_locale_report_v1 as locale


def _status(language):
    canonical = {
        "report_id": "report_readonly_fixture",
        "report_language": language,
        "identity": {
            "run_id": "comprun_readonly_fixture",
            "repository": "owner/ordinary",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_readonly_fixture",
            "report_language": language,
        },
        "assessment": {"technical_score": 90, "report_language": language},
        "bulk_presentation": [{"text": "Retained evidence ñ", "values": list(range(30))}] * 500,
    }
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, invariant=1)
    pdf.drawString(40, 750, "Ordinary retained report" if language == "en" else "Informe retenido ordinario")
    pdf.save()
    data = buffer.getvalue()
    return {
        "run_id": canonical["identity"]["run_id"],
        "repository": canonical["identity"]["repository"],
        "commit_sha": canonical["identity"]["commit_sha"],
        "evidence_ledger_id": canonical["identity"]["evidence_ledger_id"],
        "report_language": language, "terminal": True,
        "status": "pending_human_approval",
        "human_review_required": True, "human_review_completed": False,
        "client_delivery_allowed": False,
        "reports": {
            "report_id": canonical["report_id"], "json": canonical,
            "canonical_truth_sha256": locale.controller_module.canonical_sha256(canonical),
            "markdown": "# retained report", "html": "<p>retained report</p>",
            "pdf_base64": base64.b64encode(data).decode(),
            "pdf_sha256": hashlib.sha256(data).hexdigest(),
        },
    }, data


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_frozen_pdf_validates_without_cloning_canonical_presentation(monkeypatch, language):
    status, expected = _status(language)
    before = deepcopy(status)
    canonical = status["reports"]["json"]
    original_copy = locale.deepcopy
    canonical_copies = []

    def observed(value, *args, **kwargs):
        if isinstance(value, dict) and "bulk_presentation" in value:
            canonical_copies.append(True)
        return original_copy(value, *args, **kwargs)

    monkeypatch.setattr(locale, "deepcopy", observed)
    response = locale._frozen_source_pdf_response(status, language)
    assert response.body == expected
    assert response.headers["x-nico-canonical-truth-sha256"] == status["reports"]["canonical_truth_sha256"]
    assert response.headers["x-nico-client-delivery-allowed"] == "false"
    assert not canonical_copies
    assert status == before

    # Identical PDF bytes do not supply stale identity or lifecycle authority.
    status["run_id"] = "comprun_other"
    with pytest.raises(ValueError, match="status_canonical_run_id_mismatch"):
        locale._frozen_source_pdf_response(status, language)
    status["run_id"] = before["run_id"]
    status.update(status="approved", human_review_completed=False)
    with pytest.raises(ValueError, match="authoritative_approved_state_requires_completed_review"):
        locale._frozen_source_pdf_response(status, language)
    status.update(status="pending_human_approval", human_review_completed=False)
    canonical["assessment"]["technical_score"] = 91
    with pytest.raises(ValueError, match="canonical_truth_hash_mismatch"):
        locale._frozen_source_pdf_response(status, language)


def test_literal_search_does_not_classify_plain_string_leaves_as_mappings(monkeypatch):
    checks = []

    class CountingMeta(type):
        def __instancecheck__(self, value):
            if type(value) is str:
                checks.append(True)
            return isinstance(value, RealMapping)

    class CountedMapping(metaclass=CountingMeta):
        pass

    monkeypatch.setattr(commercial, "Mapping", CountedMapping)
    value = UserDict({"nested": [{"evidence": [f"literal-{i}" for i in range(1000)]}]})
    before = deepcopy(value)
    assert commercial._contains_exact_presentation_literal(value, "literal-999")
    assert not commercial._contains_exact_presentation_literal(value, "missing")
    assert not checks
    assert value == before


@pytest.mark.parametrize("value,expected", [
    ({"literal": "elsewhere"}, False),
    ({"any": ("wanted",)}, True),
    ([None, False, 12, {"nested": UserDict({"text": "wanted"})}], True),
    (["want", "wanted-extra"], False),
])
def test_literal_search_preserves_exact_nested_value_semantics(value, expected):
    assert commercial._contains_exact_presentation_literal(value, "wanted") is expected
