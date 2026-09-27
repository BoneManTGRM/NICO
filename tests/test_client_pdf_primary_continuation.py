"""Primary-section continuation pages must not be mistaken for legacy cards."""
from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from nico.client_pdf_compose_v2 import compose_compact_client_pdf
from tests.test_client_pdf_primary_finding_references import LOCALES, REFERENCES, _pdf


@pytest.mark.parametrize("register,primary,boundary", LOCALES)
@pytest.mark.parametrize("reference", REFERENCES)
@pytest.mark.parametrize("known_heading", (False, True))
def test_primary_continuation_retains_finding_references_after_register(
    register: str, primary: str, boundary: str, reference: str, known_heading: bool,
) -> None:
    heading = primary if known_heading else "Project-specific primary work package"
    base = _pdf([
        ["Cover"], [register], ["P2 · Superseded legacy finding"],
        [heading, "PRIMARY-SECTION-START"],
        ["PRIMARY-CONTINUATION-REQUIRED", reference],
    ], boundary)
    result = compose_compact_client_pdf(
        base, _pdf([["Canonical register retained"]], boundary),
        _pdf([["Human review pending; delivery blocked"]], boundary),
    )
    reader = PdfReader(io.BytesIO(result))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "PRIMARY-SECTION-START" in text
    assert "PRIMARY-CONTINUATION-REQUIRED" in text
    assert reference in text
    assert "Superseded legacy finding" not in text
    assert "Canonical register retained" in text
    assert "Human review pending; delivery blocked" in text
    assert boundary in (reader.pages[2].extract_text() or "")
    assert len(reader.pages) == 5


@pytest.mark.parametrize("register,primary,boundary", LOCALES)
def test_primary_continuation_after_shared_register_boundary_is_retained(
    register: str, primary: str, boundary: str,
) -> None:
    result = compose_compact_client_pdf(
        _pdf([["Cover"], [register, primary, "PRIMARY-SHARED-START"],
              ["PRIMARY-SHARED-CONTINUATION", REFERENCES[0]]], boundary),
        _pdf([["Canonical register retained"]], boundary),
        _pdf([["Human review pending; delivery blocked"]], boundary),
    )
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(result)).pages)
    assert "PRIMARY-SHARED-START" in text
    assert "PRIMARY-SHARED-CONTINUATION" in text
    assert REFERENCES[0] in text


@pytest.mark.parametrize("register,primary,boundary", LOCALES)
def test_new_register_boundary_resets_primary_continuation_preservation(
    register: str, primary: str, boundary: str,
) -> None:
    result = compose_compact_client_pdf(
        _pdf([["Cover"], [register], ["P2 · Superseded first finding"],
              [primary, "PRIMARY-FIRST"], [register],
              ["P2 · Superseded second finding", REFERENCES[0]],
              [primary, "PRIMARY-SECOND"]], boundary),
        _pdf([["Canonical register retained"]], boundary),
        _pdf([["Human review pending; delivery blocked"]], boundary),
    )
    reader = PdfReader(io.BytesIO(result))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "PRIMARY-FIRST" in text and "PRIMARY-SECOND" in text
    assert "Superseded first finding" not in text
    assert "Superseded second finding" not in text
    assert len(reader.pages) == 5
