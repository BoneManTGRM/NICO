from __future__ import annotations

import io

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.client_pdf_compose_v2 import compose_compact_client_pdf


def _pdf(*pages: list[str]) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=letter, invariant=1)
    for lines in pages:
        y = 740
        for line in lines:
            document.drawString(45, y, line)
            y -= 16
        document.showPage()
    document.save()
    return output.getvalue()


@pytest.mark.parametrize("title,evidence", [("Six-Month Roadmap", "Retained Evidence"),
                                           ("Hoja de ruta de seis meses", "Evidencia conservada")])
def test_companion_does_not_replace_detailed_stage_evidence_or_its_continuations(title, evidence):
    base = _pdf(["NICO COMPREHENSIVE"],
                [title, "Stage ID: six_month_roadmap", evidence, "NICO-WORK-001 retained decision"],
                [title + " — " + evidence, "NICO-WORK-002 retained dependency"],
                [title, "Generic summary replaced by the review companion"])
    result = compose_compact_client_pdf(base, _pdf(["Register"]), _pdf(["Gate"]), review_pdf=_pdf(["Review companion"]))
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(result)).pages)
    assert "NICO-WORK-001 retained decision" in text
    assert "NICO-WORK-002 retained dependency" in text
    assert "Generic summary replaced" not in text


def test_compose_uses_section_headings_not_incidental_appendix_mentions() -> None:
    base = _pdf(
        [
            "NICO COMPREHENSIVE",
            "The package includes a full evidence appendix in structured exports.",
        ],
        ["Executive Decision Brief", "Useful decision content."],
        [
            "P1 · Reduce complexity · NICO-FINDING-DUPLICATE",
            "Exact source",
            "Implementation sequence",
            "Disposition",
        ],
        ["Evidence Appendix", "raw internal material"],
        ["This page is after the appendix and must never be retained."],
    )
    register = _pdf(["Compact Finding and Remediation Register", "Complete Exact-Source Index"])
    gate = _pdf(["Human Review and Acceptance Gate", "CLIENT DELIVERY BLOCKED"])

    result = compose_compact_client_pdf(base, register, gate)
    reader = PdfReader(io.BytesIO(result))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == 4
    assert "full evidence appendix in structured exports" in extracted
    assert "Useful decision content" in extracted
    assert "NICO-FINDING-DUPLICATE" not in extracted
    assert "raw internal material" not in extracted
    assert "after the appendix" not in extracted
    assert "Complete Exact-Source Index" in extracted
    assert "Human Review and Acceptance Gate" in extracted


def test_compose_never_silently_drops_late_primary_semantic_sections() -> None:
    ordinary_pages = [
        [f"Primary evidence section {index}", f"Retained evidence line {index}"]
        for index in range(1, 43)
    ]
    base = _pdf(
        *ordinary_pages,
        ["Evidence Reconciliation and Scoring", "Canonical score reconciliation retained."],
        [
            "Executive Risk Register and Decision Briefing",
            "Executive risk decision evidence retained.",
        ],
    )
    register = _pdf(["Compact Finding and Remediation Register", "Register retained."])
    gate = _pdf(["Human Review and Acceptance Gate", "Gate retained."])

    result = compose_compact_client_pdf(base, register, gate)
    reader = PdfReader(io.BytesIO(result))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == 46
    assert "Evidence Reconciliation and Scoring" in extracted
    assert "Canonical score reconciliation retained." in extracted
    assert "Executive Risk Register and Decision Briefing" in extracted
    assert "Executive risk decision evidence retained." in extracted


def test_footer_only_overflow_is_removed_before_page_budget():
    base = _pdf(*[[f"Primary evidence {i}"] for i in range(58)],
                ["NICO Comprehensive · synthetic · AUTOMATED DRAFT", "Page 59"])
    result = compose_compact_client_pdf(base, _pdf(["Register"]), _pdf(["Gate"]))
    pages = PdfReader(io.BytesIO(result)).pages
    assert len(pages) == 60
    text = "\n".join(page.extract_text() for page in pages)
    assert all(f"Primary evidence {i}" in text for i in range(58))


def test_existing_sparse_reflow_precedes_intermediate_page_budget():
    sparse = [["NICO Comprehensive · synthetic · AUTOMATED DRAFT", f"Sparse section {i}",
               "This retained synthetic evidence is a bounded observation; independent verification remains incomplete."]
              for i in range(2)]
    result = compose_compact_client_pdf(
        _pdf(*[[f"Primary evidence {i}"] for i in range(57)], *sparse),
        _pdf(["Register"]), _pdf(["Gate"]))
    pages = PdfReader(io.BytesIO(result)).pages
    assert len(pages) <= 60
    text = "\n".join(page.extract_text() for page in pages)
    assert all(f"Primary evidence {i}" in text for i in range(57))
    assert all(f"Sparse section {i}" in text for i in range(2))
    assert text.count("independent verification remains incomplete.") == 2


def test_unreflowable_content_still_fails_the_page_budget():
    with pytest.raises(ValueError, match="cannot preserve every"):
        compose_compact_client_pdf(_pdf(*[[f"Primary evidence {i}"] for i in range(59)]),
                                  _pdf(["Register"]), _pdf(["Gate"]))


@pytest.mark.parametrize(
    "heading",
    (
        "CI/CD Operational Readiness and Historical Health",
        "Preparación operativa y salud histórica de CI/CD",
    ),
)
def test_compose_keeps_one_authoritative_ci_boundary_body_page(heading: str) -> None:
    base = _pdf(
        ["NICO COMPREHENSIVE"],
        [heading, "Superseded base boundary copy."],
        ["Client Evidence Summary", "Primary report content retained."],
    )
    ci_boundary = _pdf([heading, "Authoritative boundary copy."])
    register = _pdf(["Compact Finding and Remediation Register"])
    gate = _pdf(["Human Review and Acceptance Gate"])

    result = compose_compact_client_pdf(
        base,
        register,
        gate,
        ci_boundary_pdf=ci_boundary,
    )
    reader = PdfReader(io.BytesIO(result))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == 5
    assert extracted.count(heading) == 1
    assert "Superseded base boundary copy." not in extracted
    assert "Authoritative boundary copy." in extracted
    assert "Primary report content retained." in extracted

def test_compose_replaces_entire_legacy_detailed_register_before_budget() -> None:
    legacy_findings = [
        [
            f"P2 · Legacy finding {index} · CPP-LEGACY-{index:04d}",
            "Observed evidence retained in the machine-readable package.",
            "Recommendation retained in the compact canonical register.",
        ]
        for index in range(75)
    ]
    base = _pdf(
        ["NICO COMPREHENSIVE"],
        ["Detailed Findings Register"],
        *legacy_findings,
        ["Six-Month Execution Roadmap", "Roadmap decision content retained."],
        ["Evidence Appendix", "raw internal material"],
    )
    register = _pdf(
        ["Compact Finding and Remediation Register", "Canonical register retained."]
    )
    gate = _pdf(["Human Review and Acceptance Gate", "CLIENT DELIVERY BLOCKED"])

    result = compose_compact_client_pdf(base, register, gate)
    reader = PdfReader(io.BytesIO(result))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == 4
    assert "Detailed Findings Register" not in extracted
    assert "Legacy finding 0" not in extracted
    assert "Legacy finding 74" not in extracted
    assert "Roadmap decision content retained." in extracted
    assert "Canonical register retained." in extracted
    assert "Human Review and Acceptance Gate" in extracted
    assert "raw internal material" not in extracted


_COVER_TARGET = "c33b5b0329973c2065868eb2e7f07fab4df31f11"
_COVER_RUN = "owned-negative-report-control"
_COVER_GENERATED = "2026-10-01T16:00:00Z"
_COVER_TEXT = {
    "en": ("Comprehensive Technical Assessment", "Immutable commit:", "Run ID:", "Generated:",
           "Document page 3 of 22"),
    "es-MX": ("Evaluación Técnica Integral", "Commit inmutable:", "ID de ejecución:", "Generado:",
              "Página del documento 3 de 22"),
}


def _legacy_cover_lines(language: str, *, branded: bool) -> list[str]:
    from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY, ES_BOUNDARY

    title, commit, run, generated, footer = _COVER_TEXT[language]
    boundary = EN_BOUNDARY if language == "en" else ES_BOUNDARY
    return [
        "NICO Comprehensive · owned-negative-report-control · " + boundary,
        boundary,
        *(["NICO"] if branded else []),
        title,
        "owned/in-memory-control",
        f"{commit} {_COVER_TARGET}",
        f"{run} {_COVER_RUN}",
        f"{generated} {_COVER_GENERATED}",
        footer,
    ]


@pytest.mark.parametrize("language", ("en", "es-MX"))
@pytest.mark.parametrize("branded", (False, True))
def test_compose_removes_only_secondary_legacy_cover(language: str, branded: bool) -> None:
    secondary = _legacy_cover_lines(language, branded=branded)
    primary = ["NICO COMPREHENSIVE", "Primary cover retained."]
    evidence = [
        "Native execution evidence",
        f"Source commit: {_COVER_TARGET}",
        "Required 3; executed 3; passed 2; failed 1; skipped 0.",
        "tests_passed=false; deliberate target return 7.",
    ]
    result = compose_compact_client_pdf(
        _pdf(primary, secondary, evidence), _pdf(["Register retained."]), _pdf(["Gate retained."])
    )
    pages = PdfReader(io.BytesIO(result)).pages
    text = "\n".join(page.extract_text() or "" for page in pages)

    assert len(pages) == 4
    assert "Primary cover retained." in pages[0].extract_text()
    assert _COVER_TEXT[language][0] not in text
    assert f"Source commit: {_COVER_TARGET}" in text
    assert "Required 3; executed 3; passed 2; failed 1; skipped 0." in text
    assert "tests_passed=false; deliberate target return 7." in text
    assert "Register retained." in text
    assert "Gate retained." in text


@pytest.mark.parametrize("language", ("en", "es-MX"))
@pytest.mark.parametrize("branded", (False, True))
@pytest.mark.parametrize("content", (
    "native_failure", "unknown_body", "metadata_without_cover",
    "incidental_title", "title_prefix",
))
def test_compose_preserves_substantive_or_unrecognized_cover_like_pages(
    language: str, branded: bool, content: str,
) -> None:
    title = _COVER_TEXT[language][0]
    if content == "native_failure":
        page = _legacy_cover_lines(language, branded=branded) + [
            "Required 3; executed 3; passed 2; failed 1; skipped 0.",
            "tests_passed=false; deliberate target return 7.",
        ]
    elif content == "unknown_body":
        page = _legacy_cover_lines(language, branded=branded) + ["Unknown evidence retained."]
    elif content == "metadata_without_cover":
        page = [title, "src/net.cpp"]
    elif content == "incidental_title":
        page = ["Native evidence retained.", title, "tests_passed=false."]
    else:
        page = [title + " — native evidence retained.", "tests_passed=false."]
    if branded and content not in ("native_failure", "unknown_body"):
        page.insert(0, "NICO")
    result = compose_compact_client_pdf(
        _pdf(["Primary cover retained."], page),
        _pdf(["Register retained."]), _pdf(["Gate retained."]),
    )
    pages = PdfReader(io.BytesIO(result)).pages
    text = "\n".join(p.extract_text() or "" for p in pages)

    assert len(pages) == 4
    for line in page:
        assert line in text
    assert "Register retained." in text
    assert "Gate retained." in text


@pytest.mark.parametrize("language", ("en", "es-MX"))
def test_compose_preserves_first_cover_even_when_it_has_legacy_metadata(language: str) -> None:
    primary = _legacy_cover_lines(language, branded=True)
    result = compose_compact_client_pdf(
        _pdf(primary, ["Native evidence retained."]),
        _pdf(["Register retained."]), _pdf(["Gate retained."]),
    )
    pages = PdfReader(io.BytesIO(result)).pages

    assert len(pages) == 4
    assert _COVER_TEXT[language][0] in pages[0].extract_text()
    assert _COVER_TARGET in pages[0].extract_text()

@pytest.mark.parametrize("language", ("en", "es-MX"))
@pytest.mark.parametrize("invalid", ("empty_fields", "evidence_in_generated", "evidence_in_run", "invalid_commit"))
def test_compose_preserves_invalid_or_substantive_legacy_metadata(language: str, invalid: str) -> None:
    page = _legacy_cover_lines(language, branded=True)
    _, commit_label, run_label, generated_label, _ = _COVER_TEXT[language]
    replacements = {
        "empty_fields": {
            f"{commit_label} {_COVER_TARGET}": commit_label,
            f"{run_label} {_COVER_RUN}": run_label,
            f"{generated_label} {_COVER_GENERATED}": generated_label,
        },
        "evidence_in_generated": {
            f"{generated_label} {_COVER_GENERATED}":
                generated_label + " tests_passed=false; required=3, failed=1; native evidence retained.",
        },
        "evidence_in_run": {
            f"{run_label} {_COVER_RUN}": run_label + " Required 3; failed 1; evidence retained.",
        },
        "invalid_commit": {f"{commit_label} {_COVER_TARGET}": commit_label + " unknown-source"},
    }[invalid]
    page = [replacements.get(line, line) for line in page]
    result = compose_compact_client_pdf(
        _pdf(["Primary cover retained."], page),
        _pdf(["Register retained."]), _pdf(["Gate retained."]),
    )
    pages = PdfReader(io.BytesIO(result)).pages
    text = "\n".join(p.extract_text() or "" for p in pages)

    assert len(pages) == 4
    for line in page:
        assert line in text

@pytest.mark.parametrize("language", ("en", "es-MX"))
@pytest.mark.parametrize("invalid", ("offset_minute_99", "offset_minute_60", "duplicate_commit"))
def test_compose_preserves_invalid_offset_or_conflicting_cover_identity(language: str, invalid: str) -> None:
    page = _legacy_cover_lines(language, branded=True)
    _, commit_label, _, generated_label, _ = _COVER_TEXT[language]
    if invalid == "duplicate_commit":
        page.append(commit_label + " " + "a" * 40)
    else:
        timestamp = "2026-10-01T16:00:00+06:99" if invalid == "offset_minute_99" else "2026-10-01T16:00:00+00:60"
        page = [generated_label + " " + timestamp if line.startswith(generated_label) else line for line in page]
    result = compose_compact_client_pdf(
        _pdf(["Primary cover retained."], page),
        _pdf(["Register retained."]), _pdf(["Gate retained."]),
    )
    pages = PdfReader(io.BytesIO(result)).pages
    text = "\n".join(p.extract_text() or "" for p in pages)

    assert len(pages) == 4
    for line in page:
        assert line in text


# REP-004: production PDFs retain a host-qualified repository identity and may
# wrap the exact Spanish approval footer. These are identity-only covers; the
# primary page and any substantive/native failure evidence must still survive.
@pytest.mark.parametrize("language", ("en", "es-MX"))
@pytest.mark.parametrize("repository", (
    "owned/in-memory-control",
    "gitlab.com/gitlab-org/gitlab-test",
    "github.com/BoneManTGRM/NICO",
    "https://gitlab.com/gitlab-org/gitlab-test",
))
@pytest.mark.parametrize("wrapped", (False, True))
def test_compose_production_host_identity_and_wrapped_boundary(
    language: str, repository: str, wrapped: bool,
) -> None:
    from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY, ES_BOUNDARY

    boundary = EN_BOUNDARY if language == "en" else ES_BOUNDARY
    page = _legacy_cover_lines(language, branded=True)
    page = [repository if line == "owned/in-memory-control" else line for line in page]
    if wrapped:
        page = [part for line in page for part in
                (boundary.rsplit(" ", 1) if line == boundary else [line])]
    evidence = [
        "Native execution evidence",
        f"Source commit: {_COVER_TARGET}",
        "Required 3; executed 3; passed 2; failed 1; skipped 0.",
        "tests_passed=false; deliberate target return 7.",
    ]
    result = compose_compact_client_pdf(
        _pdf(["Primary cover retained."], page, evidence),
        _pdf(["Register retained."]), _pdf(["Gate retained."]),
    )
    pages = PdfReader(io.BytesIO(result)).pages
    text = "\n".join(p.extract_text() or "" for p in pages)

    assert len(pages) == 4
    assert "Primary cover retained." in pages[0].extract_text()
    assert _COVER_TEXT[language][0] not in text
    for line in evidence:
        assert line in text
    assert "Register retained." in text
    assert "Gate retained." in text


@pytest.mark.parametrize("language", ("en", "es-MX"))
@pytest.mark.parametrize("fault", (
    "native_failure", "unknown_path", "partial_boundary",
    "interleaved_boundary", "duplicate_identity",
))
def test_compose_production_cover_preserves_controlled_faults(
    language: str, fault: str,
) -> None:
    from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY, ES_BOUNDARY

    boundary = EN_BOUNDARY if language == "en" else ES_BOUNDARY
    page = _legacy_cover_lines(language, branded=True)
    page = ["gitlab.com/gitlab-org/gitlab-test"
            if line == "owned/in-memory-control" else line for line in page]
    if fault == "native_failure":
        page.append("tests_passed=false; required=3; failed=1; native evidence retained.")
    elif fault == "unknown_path":
        page.append("src/net.cpp/native-evidence")
    elif fault in ("partial_boundary", "interleaved_boundary"):
        parts = boundary.rsplit(" ", 1)
        replacement = parts[:1] if fault == "partial_boundary" else [
            parts[0], "Unknown evidence retained.", parts[1],
        ]
        page = [part for line in page for part in
                (replacement if line == boundary else [line])]
    else:
        page.append(_COVER_TEXT[language][1] + " " + "a" * 40)
    result = compose_compact_client_pdf(
        _pdf(["Primary cover retained."], page),
        _pdf(["Register retained."]), _pdf(["Gate retained."]),
    )
    pages = PdfReader(io.BytesIO(result)).pages
    text = "\n".join(p.extract_text() or "" for p in pages)

    assert len(pages) == 4
    for line in page:
        assert line in text


@pytest.mark.parametrize("language", ("en", "es-MX"))
def test_compose_production_cover_identity_order_does_not_hide_evidence(language: str) -> None:
    page = _legacy_cover_lines(language, branded=True)
    repository_index = page.index("owned/in-memory-control")
    metadata = page[repository_index + 1:-1]
    page[repository_index + 1:-1] = list(reversed(metadata))
    result = compose_compact_client_pdf(
        _pdf(["Primary cover retained."], page),
        _pdf(["Register retained."]), _pdf(["Gate retained."]),
    )
    assert len(PdfReader(io.BytesIO(result)).pages) == 3
