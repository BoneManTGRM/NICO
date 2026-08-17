from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


_REVIEW_SECTION_IDS = (
    "functional_qa",
    "platform_parity",
    "historical_trends_and_change_failure",
    "requirements_traceability",
    "stakeholder_and_business_alignment",
    "risk_reduction_and_executive_briefing",
    "six_month_roadmap",
    "staffing_sequencing_and_cost",
)


def _shape(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shape(item) for item in value]
    return type(value).__name__


def test_spanish_review_copy_is_derived_from_the_english_section_contract() -> None:
    from nico.comprehensive_client_review_companion_v5 import _base_section_details

    for section_id in _REVIEW_SECTION_IDS:
        english = _base_section_details(section_id, spanish=False)
        spanish = _base_section_details(section_id, spanish=True)
        assert _shape(spanish) == _shape(english)
        for field in ("can_conclude", "cannot_conclude", "required_input"):
            assert len(spanish[field]) == len(english[field])

    assert (
        "Ningún fallo terminal de ejecución de analizadores se trata como aceptación funcional."
        in _base_section_details("functional_qa", spanish=True)["can_conclude"]
    )
    assert (
        "La madurez de la configuración inmutable de CI permanece separada de los resultados históricos."
        in _base_section_details(
            "historical_trends_and_change_failure",
            spanish=True,
        )["can_conclude"]
    )


def test_spanish_decision_summary_is_localized_before_pdf_layout() -> None:
    from nico import comprehensive_report_package as report_package
    from nico.comprehensive_decision_summary_truth_v1 import (
        install_comprehensive_decision_summary_truth_v1,
    )

    install_comprehensive_decision_summary_truth_v1()
    summary = report_package._decision_summary(
        {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "report_language": "es-MX",
        },
        {
            "report_language": "es-MX",
            "limited_review_section_count": 7,
            "maturity_signal": {"level": "Sólido", "score": 89},
        },
        [],
    )

    assert summary.startswith(
        "NICO generó un borrador automatizado de Evaluación Técnica Integral"
    )
    assert "7 secciones de revisión del cliente" in summary
    assert "autorización de entrega al cliente" in summary
    assert "NICO generated an automated" not in summary

    limited_summary = report_package._decision_summary(
        {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "report_language": "es-MX",
        },
        {
            "report_language": "es-MX",
            "maturity_signal": {"level": "Sólido", "score": 89},
        },
        [{"title": "QA funcional", "status": "failed"}],
    )
    assert (
        "1 etapa automatizada tiene una limitación terminal de ejecución: QA funcional."
        in limited_summary
    )
    assert "Ninguna etapa automatizada" not in limited_summary


def test_spanish_canonical_localization_preserves_machine_truth_and_translates_native_copy() -> None:
    import pytest

    from nico.comprehensive_spanish_canonical_report_v87 import (
        _localize_tree,
        _render_inputs,
        _translate_presentation,
        render_spanish_markdown,
        render_spanish_pdf,
    )

    machine_truth = {
        "status": "blocked",
        "state": "unavailable",
        "execution_status": "failed",
        "presented_status": "review_required",
        "path": "apps/web/app/operations/page.tsx",
        "source_excerpt": 'if status == "FAILED":',
        "summary": (
            "Exact-commit executable source signals were analyzed without "
            "promoting comments, strings, detector definitions, examples, or tests."
        ),
    }
    localized = _localize_tree(machine_truth)
    for key in ("status", "state", "execution_status", "presented_status", "path", "source_excerpt"):
        assert localized[key] == machine_truth[key]
    assert localized["summary"].startswith(
        "Se analizaron las señales ejecutables del código fuente del commit exacto"
    )

    native_copy = (
        "No lockfile evidence was found in the captured snapshot.",
        "One or more dependency analyzers were unavailable.",
        "Workflow files at assessed commit: 40.",
        "Historical workflow, job, and deployment outcomes are retained as an unscored operational trend.",
        "The delivery-capacity score is 60% architecture maintainability and 40% immutable workflow automation.",
        "Commit, pull-request, merge, job, and deployment counts are retained as trend context and have no score effect.",
        "3 material scanner finding(s) require immediate human disposition.",
        "3 review_required scanner candidate(s) were retained by count, but their raw payloads were unavailable to the canonical finding register.",
    )
    for source in native_copy:
        translated = _translate_presentation(source)
        assert translated != source
        assert not any(
            marker in translated
            for marker in (
                "lockfile evidence",
                "dependency analyzers were unavailable",
                "Workflow files at assessed commit",
                "are retained as an unscored",
                "delivery-capacity score",
                "have no score effect",
                "scanner finding(s)",
                "scanner candidate(s)",
            )
        )

    with pytest.raises(ValueError, match="missing Spanish presentation translation for summary"):
        _localize_tree(
            {
                "summary": (
                    "The newly introduced workflow summary remains pending human review."
                )
            }
        )

    raw_scanner_message = (
        "The application does not verify the token before the request is authorized."
    )
    _, localized_assessment, _, _ = _render_inputs(
        {
            "identity": {},
            "assessment": {
                "canonical_scanner_finding_register": {
                    "findings": [{"evidence": raw_scanner_message}]
                }
            },
            "stage_summaries": [],
        }
    )
    assert (
        localized_assessment["canonical_scanner_finding_register"]["findings"][0]["evidence"]
        == raw_scanner_message
    )

    collision_canonical = {
        "identity": {
            "repository": "Org/Pending",
            "run_id": "GREEN",
            "commit_sha": "abc123",
            "evidence_ledger_id": "YELLOW",
            "customer_id": "BLOCKED",
            "project_id": "UNAVAILABLE",
            "report_language": "es-MX",
        },
        "assessment": {
            "sections": [
                {
                    "id": "code_audit",
                    "label": "Code Audit",
                    "status": "green",
                    "presented_status": "green",
                    "score": 100,
                    "presented_score": 100,
                    "summary": "Exact-commit sampled code signals and repository structure were reviewed.",
                    "evidence": [],
                    "findings": [],
                    "unavailable": [],
                }
            ],
            "maturity_signal": {},
        },
        "stage_summaries": [],
    }
    collision_markdown = render_spanish_markdown(collision_canonical)
    collision_pdf, _ = render_spanish_pdf(collision_canonical)
    from pypdf import PdfReader
    import io

    collision_pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(collision_pdf)).pages
    )
    for literal in (
        "Org/Pending",
        "GREEN",
        "YELLOW",
        "BLOCKED",
        "UNAVAILABLE",
    ):
        assert literal in collision_markdown
    for literal in (
        "Org/Pending",
        "GREEN",
        "BLOCKED",
        "UNAVAILABLE",
    ):
        assert literal in collision_pdf_text
    assert "VERDE" in collision_markdown
    assert "VERDE" in collision_pdf_text


def test_same_canonical_package_has_exact_spanish_publication_parity() -> None:
    """Exercise both locales through the terminal production report stack."""

    repository_root = Path(__file__).resolve().parents[1]
    script = r'''
import base64
import copy
import hashlib
import html
import io
import re

from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth

from tests.test_comprehensive_report_package_v2 import _package as rich_package
from tests.test_phase9_comprehensive_report_integration_v1 import _result as phase9_result
from tests.test_v2_premium_report_renderer import _package as small_package
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package
from nico.comprehensive_spanish_client_surface_localization_v86 import (
    install_comprehensive_spanish_client_surface_localization_v86,
)


install_comprehensive_spanish_client_surface_localization_v86()

SMALL_ENGLISH_GOLDEN = {
    "markdown": ("763071604b1a2ca9fbe0f7394a0cbd58987a9dfd149104c0fb59a0a4ac6a7f71", 17916),
    "html": ("874596a1e852c3f786c01c880041efa50e9ba2ec7e705b4802a636dcdf473fbb", 21451),
    "pdf_base64": ("10784b2a3b3ed7a9cda5442aaf552da3f01cdbaeae6b3deeb27ac0ee8a0f5ee6", 169412),
    "pdf_sha256": "43de89942fc80bb5360e79fe560117383135c4b001eb3d23900ef7da2f7e92dd",
    "page_count": 22,
}
RICH_ENGLISH_GOLDEN = {
    "markdown": ("cf32983fea08eb8f0987b8d86a0f30410644e142593b8a64e74b687f3a557a62", 20594),
    "html": ("f74be5318d9787f60cba203bb83ac186e1b84e9415a1612cb10b85058c6f3082", 24690),
    "pdf_base64": ("3d24f1b1bc2043a6440686c5c9b36da64a37fd33281251edae60b8b0101e60d0", 254420),
    "pdf_sha256": "b4c81bf43cbc9ef5f0ee43bfdaf9bbc3af1aae41d8d77920d0850f5dead53eca",
    "page_count": 39,
}
PHASE9_ENGLISH_GOLDEN = {
    "markdown": ("f455d33de53683b5248d0a250dc7446d4f879a7d944f66ec1f359c0b378da9c2", 18652),
    "html": ("8f773349d8722e007b2340c64946c1d187cd275b3e3e82a5961ff4b8ffd96dfd", 22511),
    "pdf_base64": ("fbbbd74488b9f9d20bf5f0b74393a348c7191b24014f21e92b37de6037e75681", 166016),
    "pdf_sha256": "f51c02f63babb806445d50479604793ab185bc7c739e3cad3e562e932c8ef022",
    "page_count": 21,
}

SPANISH_OUTLINE = {
    "Table of Contents": "Índice",
    "Comprehensive Technical Assessment": "Evaluación Técnica Integral",
    "Executive Decision Brief": "Resumen ejecutivo para decisiones",
    "Priority Constraints and Decision Risks": "Restricciones prioritarias y riesgos de decisión",
    "Canonical Technical Scorecard": "Cuadro de puntuación técnica",
    "Code Audit": "Auditoría de código",
    "Dependency / Library Ecosystem": "Ecosistema de dependencias y bibliotecas",
    "Secrets Exposure Review": "Revisión de exposición de secretos",
    "Static Analysis": "Análisis estático",
    "CI/CD Analysis": "Análisis de CI/CD",
    "Architecture & Technical Debt": "Arquitectura y deuda técnica",
    "Velocity / Complexity": "Velocidad y complejidad",
    "Repository and Delivery Evidence": "Evidencia del repositorio y de entrega",
    "Evidence Reconciliation and Scoring": "Conciliación y puntuación de evidencia",
    "Architecture and Data Flow": "Arquitectura y flujo de datos",
    "Developer Delivery Process": "Proceso de entrega de desarrollo",
    "Historical Trends and Change Failure": "Tendencias históricas y fallos de cambio",
    "Authorization and Scope": "Autorización y alcance",
    "Dependency, Security, and Static Analysis": "Dependencias, seguridad y análisis estático",
    "CI/CD, Architecture, Complexity, and Velocity": "CI/CD, arquitectura, complejidad y velocidad",
    "Risk Reduction and Executive Briefing": "Reducción de riesgo y resumen ejecutivo",
    "CI/CD Operational Readiness and Historical Health": "Preparación operativa y salud histórica de CI/CD",
    "Compact Finding and Remediation Register": "Registro compacto de hallazgos y remediación",
    "Complete Exact-Source Index": "Índice completo de fuentes exactas",
    "Client Evidence Summary": "Resumen de evidencia del cliente",
    "Human Review and Acceptance Gate": "Puerta de revisión humana y aceptación",
    "Client Artifact Manifest": "Manifiesto de artefactos del cliente",
    "Human Review and Exact-Artifact Approval Record": "Registro de revisión humana y aprobación de artefactos exactos",
}


def render(package):
    result = rebuild_client_artifacts(copy.deepcopy(package))
    pdf = base64.b64decode(result["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    pages = [page.extract_text() or "" for page in reader.pages]
    return result, reader, pages


def render_phase9(package):
    result = finalize_report_package(copy.deepcopy(package))["report_package"]
    pdf = base64.b64decode(result["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    pages = [page.extract_text() or "" for page in reader.pages]
    return result, reader, pages


def rich_input(language):
    canonical = copy.deepcopy(rich_package()["report_package"]["json"])
    generated_at = "2026-08-04T16:15:00Z"
    canonical.update(
        {
            "report_language": language,
            "locale": language,
            "generated_at": generated_at,
            "generation_timestamp": generated_at,
        }
    )
    canonical["identity"].update(
        {"report_language": language, "generated_at": generated_at}
    )
    canonical["assessment"]["report_language"] = language
    return {"json": canonical}


def phase9_input(language):
    package = copy.deepcopy(phase9_result())
    canonical = package["report_package"]["json"]
    canonical.update({"report_language": language, "locale": language})
    canonical["identity"].update(
        {"report_language": language, "locale": language}
    )
    canonical["assessment"].update(
        {"report_language": language, "locale": language}
    )
    return package


def fingerprint(result):
    output = {}
    for field in ("markdown", "html", "pdf_base64"):
        value = result[field]
        output[field] = (hashlib.sha256(value.encode("utf-8")).hexdigest(), len(value))
    output["pdf_sha256"] = result["pdf_sha256"]
    output["page_count"] = result["pdf_page_count"]
    return output


def markdown_signature(markdown):
    output = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--"):
            continue
        heading = re.match(r"^(#{1,6})\s", line)
        if heading:
            output.append(f"h{len(heading.group(1))}")
        elif line.startswith("- [ ]"):
            output.append("check")
        elif line.startswith("- "):
            output.append("li")
        elif re.fullmatch(r"\|.*\|", line):
            output.append("table")
        else:
            output.append("p")
    return output


def html_signature(rendered):
    return re.findall(r"<(/?[A-Za-z][\w-]*)\b", rendered)


def outline_projection(reader):
    return [
        (getattr(item, "title", str(item)), reader.get_destination_page_number(item) + 1)
        for item in reader.outline
    ]


def assert_pdf_text_within_media_box(reader):
    violations = []
    for page_number, page in enumerate(reader.pages, start=1):
        left = float(page.mediabox.left)
        right = float(page.mediabox.right)

        def visit(text, cm, tm, font, font_size):
            value = str(text or "").rstrip("\n")
            if not value:
                return
            font_name = str((font or {}).get("/BaseFont") or "/Helvetica")
            font_name = font_name.split("+")[-1].lstrip("/") or "Helvetica"
            try:
                width = stringWidth(value, font_name, font_size)
            except Exception:
                width = stringWidth(value, "Helvetica", font_size)
            origin = cm[4] + (tm[4] * cm[0]) + (tm[5] * cm[2])
            horizontal_scale = abs((tm[0] * cm[0]) + (tm[1] * cm[2])) or 1.0
            edge = origin + (width * horizontal_scale)
            if origin < left - 0.5 or edge > right + 0.5:
                violations.append((page_number, origin, edge, value))

        page.extract_text(visitor_text=visit)
    assert not violations, violations[:10]


def truth_projection(result):
    canonical = result["json"]
    assessment = canonical.get("assessment") or {}
    return {
        "identity": {
            key: value
            for key, value in (canonical.get("identity") or {}).items()
            if key not in {"report_language", "locale"}
        },
        "scores": (
            assessment.get("technical_score"),
            assessment.get("canonical_evidence_adjusted_score"),
            (assessment.get("maturity_signal") or {}).get("score"),
        ),
        "controls": [
            (
                item.get("id"),
                item.get("score"),
                item.get("presented_score"),
                item.get("status"),
                len(item.get("evidence") or []),
                len(item.get("findings") or []),
            )
            for item in assessment.get("sections") or []
        ],
        "stages": [
            (item.get("stage_id"), item.get("status"))
            for item in canonical.get("stage_summaries") or []
        ],
        "findings": [
            (item.get("finding_id"), item.get("priority"), item.get("location"))
            for item in canonical.get("canonical_findings") or []
        ],
        "artifact_types": [
            item.get("artifact_type")
            for item in (result.get("artifact_manifest") or {}).get("artifacts") or []
        ],
        "review": (
            result.get("human_review_required"),
            result.get("client_delivery_allowed"),
            result.get("report_finality"),
        ),
    }


def assert_exact_manifest(result):
    fields = {
        "findings_csv": "findings_csv",
        "evidence_csv": "evidence_csv",
        "candidate_register_json": "candidate_register_json",
        "remediation_backlog_json": "remediation_backlog_json",
        "markdown_report": "markdown",
        "html_report": "html",
        "canonical_json": "canonical_json",
    }
    entries = (result.get("artifact_manifest") or {}).get("artifacts") or []
    assert len(entries) == 8
    for entry in entries:
        artifact_type = entry["artifact_type"]
        if artifact_type == "comprehensive_pdf":
            retained = base64.b64decode(result["pdf_base64"])
        else:
            retained = result[fields[artifact_type]].encode("utf-8")
        assert hashlib.sha256(retained).hexdigest() == entry["sha256"]
        assert len(retained) == entry["size_bytes"]


def assert_structural_parity(english, spanish):
    en_result, en_reader, en_pages = english
    es_result, es_reader, es_pages = spanish
    assert len(es_pages) == len(en_pages)
    assert markdown_signature(es_result["markdown"]) == markdown_signature(en_result["markdown"])
    assert html_signature(es_result["html"]) == html_signature(en_result["html"])
    assert truth_projection(es_result) == truth_projection(en_result)

    en_outline = outline_projection(en_reader)
    es_outline = outline_projection(es_reader)
    assert [page for _, page in es_outline] == [page for _, page in en_outline]
    assert [title for title, _ in es_outline] == [
        SPANISH_OUTLINE[title] for title, _ in en_outline
    ]
    assert_pdf_text_within_media_box(es_reader)

    en_toc = en_pages[1]
    es_toc = es_pages[1]
    for title, page in en_outline[1:]:
        assert f"{title}\n{page}" in en_toc
    for title, page in es_outline[1:]:
        assert f"{title}\n{page}" in es_toc

    for index, (en_page, es_page) in enumerate(
        zip(en_reader.pages, es_reader.pages),
        start=1,
    ):
        assert list(en_page.mediabox) == list(es_page.mediabox)
        assert (en_page.rotation or 0) == (es_page.rotation or 0)
        assert en_pages[index - 1].count(
            f"Document page {index} of {len(en_pages)}"
        ) == 1
        assert es_pages[index - 1].count(
            f"Página del documento {index} de {len(es_pages)}"
        ) == 1
        assert len(" ".join(es_pages[index - 1].split())) >= 120


small_english_before = render(small_package("en"))
small_spanish = render(small_package("es-MX"))
small_english_after = render(small_package("en"))

assert fingerprint(small_english_before[0]) == SMALL_ENGLISH_GOLDEN
assert fingerprint(small_english_after[0]) == SMALL_ENGLISH_GOLDEN
assert small_english_before[0]["markdown"] == small_english_after[0]["markdown"]
assert small_english_before[0]["html"] == small_english_after[0]["html"]
assert small_english_before[0]["pdf_base64"] == small_english_after[0]["pdf_base64"]
assert "spanish_uses_english_canonical_section_contract" not in small_english_before[0]["premium_report_renderer"]
assert small_spanish[0]["premium_report_renderer"]["spanish_uses_english_canonical_section_contract"] is True
assert_structural_parity(small_english_before, small_spanish)

rich_english = render(rich_input("en"))
rich_spanish = render(rich_input("es-MX"))
assert fingerprint(rich_english[0]) == RICH_ENGLISH_GOLDEN
assert_structural_parity(rich_english, rich_spanish)
assert len(rich_english[2]) == len(rich_spanish[2]) == 39
assert len(outline_projection(rich_english[1])) == len(outline_projection(rich_spanish[1])) == 27
assert len(re.findall(r"(?m)^#{1,3}\s", rich_english[0]["markdown"])) == 87
assert len(re.findall(r"(?m)^#{1,3}\s", rich_spanish[0]["markdown"])) == 87

phase9_english = render_phase9(phase9_input("en"))
phase9_spanish = render_phase9(phase9_input("es-MX"))
assert fingerprint(phase9_english[0]) == PHASE9_ENGLISH_GOLDEN
assert_structural_parity(phase9_english, phase9_spanish)
for finding_id in (
    "NICO-FINDING-E5CA1CA5C494",
    "NICO-FINDING-94D84D011F4D",
    "ARCH-1",
):
    assert finding_id in phase9_english[0]["markdown"]
    assert finding_id in phase9_spanish[0]["markdown"]
assert "componentes hij..." not in phase9_spanish[0]["markdown"]
assert len(phase9_english[2]) == len(phase9_spanish[2]) == 21
assert len(outline_projection(phase9_english[1])) == len(outline_projection(phase9_spanish[1])) == 14
assert len(re.findall(r"(?m)^#{1,3}\s", phase9_english[0]["markdown"])) == 78
assert len(re.findall(r"(?m)^#{1,3}\s", phase9_spanish[0]["markdown"])) == 78

for result in (small_spanish[0], rich_spanish[0], phase9_spanish[0]):
    assert_exact_manifest(result)
    assert "lang='es-MX'" in result["html"] or 'lang="es-MX"' in result["html"]
    visible_markdown = re.sub(r"<!--.*?-->", "", result["markdown"], flags=re.S)
    visible_html = html.unescape(
        re.sub(r"<!--.*?-->", "", result["html"], flags=re.S)
    )
    pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(
            io.BytesIO(base64.b64decode(result["pdf_base64"]))
        ).pages
    )
    for forbidden in (
        "Executive Decision Brief",
        "Priority Constraints and Decision Risks",
        "Canonical Technical Scorecard",
        "Architecture & Technical Debt",
        "Evidence Foundation",
        "Roadmap, Resourcing, and Decision",
        "NICO generated an automated",
        "Decision-oriented summary",
        "Exact immutable evidence item",
        "Review-limited finding",
        "One bounded evidence limitation",
        "Retained finding for",
        "Human context limitation for",
        "Substantive summary for",
        "Stakeholder interviews were not supplied",
        "No retained structured stage summary",
        "Human context or additional evidence",
        "The canonical finding was retained",
        "Evidence Evaluated",
        "Evidence Bound",
        "Evidence-Adjusted",
        "Unavailable or limited evidence",
        "AUTOMATED DRAFT",
        "Not scored",
        "Not supplied",
        "Requires human technical disposition",
        "Operations route complexity is reduced",
        "scanner execution(s) remain incomplete",
        "Exact-commit executable source signals were analyzed",
        "Historical workflow, job, and deployment outcomes are retained",
        "The delivery-capacity score is",
        "Commit, pull-request, merge, job, and deployment counts are retained",
        "STRONG",
        "## Registro detallado de hallazgos",
    ):
        assert forbidden not in visible_markdown
        assert forbidden not in visible_html
        assert forbidden not in pdf_text
    assert visible_markdown.count("Analizadores aplicables incompletos:") == 1
    assert visible_html.count("Analizadores aplicables incompletos:") == 1
    assert pdf_text.count("Analizadores aplicables incompletos:") == 1
    assert "Ã" not in pdf_text
    assert "\x00" not in pdf_text

small_result, _, small_pages = small_spanish
small_pdf_text = "\n".join(small_pages)
for token in (
    "BoneManTGRM/NICO",
    "7777777777777777777777777777777777777777",
    "comprun_premium",
    "ledger-premium",
    "apps/web/app/page.tsx:100",
    "RISK-P1-001",
    "bandit",
    "completed_with_findings",
    "WP-001",
):
    assert token in small_result["markdown"]
    assert token in small_result["html"]
    assert token in small_pdf_text

for heading in (
    "Resumen ejecutivo para decisiones",
    "Cuadro de puntuación técnica",
    "Fundamento de evidencia",
    "Hoja de ruta, recursos y decisión",
    "Registro compacto de hallazgos y remediación",
    "Puerta de revisión humana y aceptación",
):
    assert heading in small_result["markdown"]
    assert heading in small_result["html"]
    assert heading in small_pdf_text

assert "ENTREGA AL CLIENTE BLOQUEADA — ENTREGA AL CLIENTE NO AUTORIZADA" in small_result["markdown"]
assert "&lt;!-- CLIENT DELIVERY NOT AUTHORIZED --&gt;" not in small_result["html"]
assert small_result["markdown"].count("## Registro compacto de hallazgos y remediación") == 1
assert small_result["markdown"].count("## Índice completo de fuentes exactas") == 1
assert small_result["markdown"].count("## Puerta de revisión humana y aceptación") == 1
'''

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, (
        "same-package English/Spanish report parity failed\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
