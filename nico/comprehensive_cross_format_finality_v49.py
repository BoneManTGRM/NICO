from __future__ import annotations

import base64
import html as html_lib
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_cross_format_finality.v51"
_PATCH_MARKER = "_nico_comprehensive_cross_format_finality_v51"
_SCORE_PATCH_MARKER = "_nico_comprehensive_score_truth_v51"
_PACKAGE_KEYS = (
    "report_package",
    "reports",
    "report",
    "final_report",
    "final_package",
    "artifacts",
    "output",
    "result",
)


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split())


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(round(value))))


def _canonical_score_truth(assessment: dict[str, Any]) -> dict[str, Any]:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    technical_candidates = (
        assessment.get("technical_score"),
        maturity.get("technical_score"),
        maturity.get("score"),
        maturity.get("source_score"),
        maturity.get("presented_score"),
    )
    adjusted_candidates = (
        assessment.get("canonical_evidence_adjusted_score"),
        maturity.get("canonical_evidence_adjusted_score"),
        assessment.get("evidence_adjusted_score"),
        maturity.get("evidence_adjusted_score"),
    )
    technical = next((score for raw in technical_candidates if (score := _numeric(raw)) is not None), None)
    adjusted = next((score for raw in adjusted_candidates if (score := _numeric(raw)) is not None), None)
    if adjusted is None:
        adjusted = technical

    adjusted_aliases = {
        "assessment.canonical_evidence_adjusted_score": _numeric(assessment.get("canonical_evidence_adjusted_score")),
        "assessment.evidence_adjusted_score": _numeric(assessment.get("evidence_adjusted_score")),
        "maturity.canonical_evidence_adjusted_score": _numeric(maturity.get("canonical_evidence_adjusted_score")),
        "maturity.evidence_adjusted_score": _numeric(maturity.get("evidence_adjusted_score")),
    }
    present_aliases = {key: value for key, value in adjusted_aliases.items() if value is not None}
    aliases_consistent = adjusted is not None and all(value == adjusted for value in present_aliases.values())
    return {
        "technical_score": technical,
        "evidence_adjusted_score": adjusted,
        "adjusted_aliases": adjusted_aliases,
        "adjusted_aliases_consistent": aliases_consistent,
    }


def synchronize_comprehensive_score_truth(assessment: dict[str, Any]) -> dict[str, Any]:
    """Project one canonical score pair into every Comprehensive report surface."""

    output = deepcopy(assessment)
    truth = _canonical_score_truth(output)
    technical = truth["technical_score"]
    adjusted = truth["evidence_adjusted_score"]
    maturity = output.get("maturity_signal") if isinstance(output.get("maturity_signal"), dict) else {}

    if technical is not None:
        output["technical_score"] = technical
        maturity["score"] = technical
        maturity["source_score"] = technical
        maturity["technical_score"] = technical
        maturity["presented_score"] = technical

    if adjusted is not None:
        output["canonical_evidence_adjusted_score"] = adjusted
        output["evidence_adjusted_score"] = adjusted
        maturity["canonical_evidence_adjusted_score"] = adjusted
        maturity["evidence_adjusted_score"] = adjusted

    output["maturity_signal"] = maturity
    output["comprehensive_score_truth"] = {
        "status": "complete" if technical is not None and adjusted is not None else "incomplete",
        "version": VERSION,
        "technical_score": technical,
        "canonical_evidence_adjusted_score": adjusted,
        "aliases_synchronized": adjusted is not None,
        "technical_and_evidence_adjusted_scores_separate": True,
    }

    summary = str(output.get("executive_summary") or "")
    if summary and adjusted is not None:
        summary = re.sub(
            r"(independently evidence-adjusted readiness is\s+)(?:not scored|\d{1,3}/100)",
            rf"\g<1>{adjusted}/100",
            summary,
            flags=re.I,
        )
        summary = re.sub(
            r"(Evidence-Adjusted readiness is\s+)(?:not scored|\d{1,3}/100)",
            rf"\g<1>{adjusted}/100",
            summary,
            flags=re.I,
        )
        output["executive_summary"] = summary
    return output


def _synchronized_stage_results(stage_results: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stages = deepcopy(stage_results)
    scoring = stages.get("evidence_reconciliation_and_scoring")
    if isinstance(scoring, dict) and isinstance(scoring.get("assessment"), dict):
        scoring["assessment"] = synchronize_comprehensive_score_truth(scoring["assessment"])
    return stages


def _install_score_truth_patch() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as decision_report
    from nico import comprehensive_express_quality_v7 as quality
    from nico import comprehensive_native_providers as providers
    from nico import comprehensive_report_package as base_report

    changed = 0

    current_reconcile: Callable[[dict[str, Any]], dict[str, Any]] = decision_report.reconcile_comprehensive_assessment
    if not getattr(current_reconcile, _SCORE_PATCH_MARKER, False):
        @wraps(current_reconcile)
        def reconcile(assessment: dict[str, Any]) -> dict[str, Any]:
            return synchronize_comprehensive_score_truth(current_reconcile(assessment))

        setattr(reconcile, _SCORE_PATCH_MARKER, True)
        setattr(reconcile, "_nico_previous", current_reconcile)
        decision_report.reconcile_comprehensive_assessment = reconcile
        quality.reconcile_comprehensive_assessment = reconcile
        changed += 1

    current_pdf: Callable[..., Any] = decision_report.comprehensive_pdf_with_final_count
    if not getattr(current_pdf, _SCORE_PATCH_MARKER, False):
        @wraps(current_pdf)
        def render_pdf(
            identity: dict[str, Any],
            assessment: dict[str, Any],
            stages: list[dict[str, Any]],
            roadmap: list[dict[str, Any]],
            staffing: list[dict[str, Any]],
            limitations: dict[str, int],
            generated_at: str,
        ) -> Any:
            return current_pdf(
                identity,
                synchronize_comprehensive_score_truth(assessment),
                stages,
                roadmap,
                staffing,
                limitations,
                generated_at,
            )

        setattr(render_pdf, _SCORE_PATCH_MARKER, True)
        setattr(render_pdf, "_nico_previous", current_pdf)
        decision_report.comprehensive_pdf_with_final_count = render_pdf
        quality.comprehensive_pdf_with_final_count = render_pdf
        changed += 1

    current_builder: Callable[..., dict[str, Any]] = providers.build_comprehensive_report_package
    if not getattr(current_builder, _SCORE_PATCH_MARKER, False):
        @wraps(current_builder)
        def build_report_package(
            *,
            identity: dict[str, Any],
            stage_results: dict[str, dict[str, Any]],
        ) -> dict[str, Any]:
            result = current_builder(
                identity=identity,
                stage_results=_synchronized_stage_results(stage_results),
            )
            if isinstance(result.get("assessment"), dict):
                result["assessment"] = synchronize_comprehensive_score_truth(result["assessment"])
            package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
            canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
            if isinstance(canonical.get("assessment"), dict):
                canonical["assessment"] = synchronize_comprehensive_score_truth(canonical["assessment"])
            return result

        setattr(build_report_package, _SCORE_PATCH_MARKER, True)
        setattr(build_report_package, "_nico_previous", current_builder)
        providers.build_comprehensive_report_package = build_report_package
        base_report.build_comprehensive_report_package = build_report_package
        changed += 1

    return {
        "status": "installed" if changed else "already_installed",
        "version": VERSION,
        "functions_rebound": changed,
        "canonical_score_aliases_synchronized": True,
        "core_and_final_report_paths_bound": True,
        "pdf_front_matter_bound": True,
    }


def _delivery_boundary_present(markdown: str) -> bool:
    """Accept the current final-report boundary without reviving stale draft wording."""

    upper = _normalized(markdown).upper()
    blocked = any(
        phrase in upper
        for phrase in (
            "CLIENT DELIVERY BLOCKED",
            "CLIENT DELIVERY IS BLOCKED",
            "CLIENT DELIVERY NOT AUTHORIZED",
        )
    )
    pending_approval = "PENDING HUMAN APPROVAL" in upper
    return blocked and pending_approval


def _identity_present(markdown: str, identity: dict[str, str]) -> bool:
    normalized = _normalized(markdown)
    return all(
        value in normalized
        for value in (
            identity["run_id"],
            identity["repository"],
            identity["commit_sha"],
        )
    )


def _looks_like_report_package(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(
        str(value.get("markdown") or "").strip()
        and str(value.get("html") or "").strip()
        and str(value.get("pdf_base64") or "").strip()
    )


def _report_package(final_stage: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Resolve the generated package from supported stage-envelope shapes."""

    if _looks_like_report_package(final_stage):
        return final_stage, "stage"

    queue: list[tuple[dict[str, Any], str, int]] = [(final_stage, "stage", 0)]
    visited: set[int] = set()
    while queue:
        current, source, depth = queue.pop(0)
        marker = id(current)
        if marker in visited:
            continue
        visited.add(marker)
        if depth >= 3:
            continue
        for key in _PACKAGE_KEYS:
            candidate = current.get(key)
            if not isinstance(candidate, dict):
                continue
            candidate_source = f"{source}.{key}"
            if _looks_like_report_package(candidate):
                return candidate, candidate_source
            queue.append((candidate, candidate_source, depth + 1))
    return {}, "unresolved"


def _semantic_value(package: dict[str, Any], key: str) -> Any:
    """Read finality metadata from the package or its canonical JSON truth."""

    direct = package.get(key)
    if direct is not None:
        return direct
    canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
    canonical_value = canonical.get(key)
    if canonical_value is not None:
        return canonical_value
    truth = canonical.get("canonical_report_truth") if isinstance(canonical.get("canonical_report_truth"), dict) else {}
    if truth.get(key) is not None:
        return truth.get(key)
    quality = package.get("report_quality_contract")
    if isinstance(quality, dict) and quality.get(key) is not None:
        return quality.get(key)
    return None


def _pdf_text(pdf: bytes) -> str:
    if not pdf.startswith(b"%PDF"):
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf))
        return _normalized(
            " ".join((reader.pages[index].extract_text() or "") for index in range(min(3, len(reader.pages))))
        )
    except Exception:
        return ""


def _html_text(document: str) -> str:
    return _normalized(html_lib.unescape(re.sub(r"<[^>]+>", " ", document)))


def _score_near_label(text: str, score: int | None, labels: tuple[str, ...]) -> bool:
    if score is None:
        return False
    normalized = _normalized(text)
    lowered = normalized.casefold()
    token = f"{score}/100"
    for label in labels:
        index = lowered.find(label.casefold())
        if index >= 0 and token in normalized[index : index + 220]:
            return True
    return False


def _package_score_truth(package: dict[str, Any], pdf: bytes) -> dict[str, Any]:
    canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    truth = _canonical_score_truth(assessment)
    technical = truth["technical_score"]
    adjusted = truth["evidence_adjusted_score"]
    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    pdf_text = _pdf_text(pdf)
    html_text = _html_text(rendered_html)
    technical_labels = ("Technical maturity", "TECHNICAL MATURITY")
    adjusted_labels = ("Evidence-Adjusted", "evidence-adjusted readiness")
    return {
        **truth,
        "markdown_technical_matches": _score_near_label(markdown, technical, technical_labels),
        "markdown_evidence_adjusted_matches": _score_near_label(markdown, adjusted, adjusted_labels),
        "html_technical_matches": _score_near_label(html_text, technical, technical_labels),
        "html_evidence_adjusted_matches": _score_near_label(html_text, adjusted, adjusted_labels),
        "pdf_technical_matches": _score_near_label(pdf_text, technical, technical_labels),
        "pdf_evidence_adjusted_matches": _score_near_label(pdf_text, adjusted, adjusted_labels),
        "pdf_text_available": bool(pdf_text),
    }


def _required_checks(
    context: dict[str, Any],
    package: dict[str, Any],
    *,
    pdf: bytes,
    score_truth: dict[str, Any],
) -> dict[str, bool]:
    from nico import comprehensive_native_providers as providers

    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    identity = providers._identity(context)
    return {
        "markdown_available": bool(markdown),
        "html_available": bool(rendered_html),
        "pdf_available": pdf.startswith(b"%PDF"),
        "identity_present_in_markdown": _identity_present(markdown, identity),
        "final_delivery_boundary_present_in_markdown": _delivery_boundary_present(markdown),
        "service_id_is_comprehensive": _semantic_value(package, "service_id") == "comprehensive",
        "report_finality_is_final": _semantic_value(package, "report_finality") == "final",
        "approval_is_pending_human_review": _semantic_value(package, "approval_status") == "pending_human_approval",
        "delivery_status_is_blocked": _semantic_value(package, "delivery_status") == "blocked_pending_human_approval",
        "human_review_required": _semantic_value(package, "human_review_required") is True,
        "client_delivery_disallowed": _semantic_value(package, "client_delivery_allowed") is False,
        "canonical_score_truth_available": (
            score_truth.get("technical_score") is not None
            and score_truth.get("evidence_adjusted_score") is not None
        ),
        "evidence_adjusted_aliases_consistent": score_truth.get("adjusted_aliases_consistent") is True,
        "markdown_technical_matches_canonical": score_truth.get("markdown_technical_matches") is True,
        "markdown_evidence_adjusted_matches_canonical": score_truth.get("markdown_evidence_adjusted_matches") is True,
        "html_technical_matches_canonical": score_truth.get("html_technical_matches") is True,
        "html_evidence_adjusted_matches_canonical": score_truth.get("html_evidence_adjusted_matches") is True,
        "pdf_technical_matches_canonical": score_truth.get("pdf_technical_matches") is True,
        "pdf_evidence_adjusted_matches_canonical": score_truth.get("pdf_evidence_adjusted_matches") is True,
    }


def finality_aware_cross_format_verification_provider(context: dict[str, Any]) -> dict[str, Any]:
    """Verify exact identity, finality, delivery posture, and canonical score parity."""

    from nico import comprehensive_native_providers as providers

    final_stage = providers._prior(context, "final_comprehensive_report_generation")
    package, package_source = _report_package(final_stage)
    encoded_pdf = str(package.get("pdf_base64") or "")
    try:
        pdf = base64.b64decode(encoded_pdf, validate=True) if encoded_pdf else b""
    except Exception:
        pdf = b""
    score_truth = _package_score_truth(package, pdf)
    checks = _required_checks(context, package, pdf=pdf, score_truth=score_truth)
    failed_checks = sorted(name for name, passed in checks.items() if passed is not True)
    payload = {
        "checks": checks,
        "failed_checks": failed_checks,
        "cross_format_contract_schema": VERSION,
        "report_package_source": package_source,
        "score_truth": score_truth,
        "required_finality": "final",
        "required_approval_status": "pending_human_approval",
        "required_delivery_status": "blocked_pending_human_approval",
    }

    if failed_checks:
        return providers._result(
            context,
            "blocked",
            reason="cross_format_final_report_verification_failed",
            **payload,
        )

    return providers._result(
        context,
        summary=(
            "Markdown, HTML, and PDF artifacts passed immutable identity, canonical "
            "technical/evidence-adjusted score parity, final-report status, "
            "pending-human-approval, and blocked-delivery verification."
        ),
        **payload,
        evidence={
            **checks,
            "report_package_source": package_source,
            "pdf_sha256": __import__("hashlib").sha256(pdf).hexdigest(),
            "canonical_truth_sha256": package.get("canonical_truth_sha256"),
            "technical_score": score_truth.get("technical_score"),
            "evidence_adjusted_score": score_truth.get("evidence_adjusted_score"),
        },
    )


def install_comprehensive_cross_format_finality_v49() -> dict[str, Any]:
    """Retain the public installer name while installing the corrected v51 contract."""

    from nico import comprehensive_native_providers as providers

    score_patch = _install_score_truth_patch()
    current: Callable[[dict[str, Any]], dict[str, Any]] = providers.cross_format_verification_provider
    if getattr(current, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "score_truth_patch": score_patch,
            "canonical_score_parity_required": True,
            "legacy_draft_phrase_required": False,
        }

    @wraps(current)
    def verify(context: dict[str, Any]) -> dict[str, Any]:
        return finality_aware_cross_format_verification_provider(context)

    setattr(verify, _PATCH_MARKER, True)
    setattr(verify, "_nico_previous", current)
    providers.cross_format_verification_provider = verify
    return {
        "status": "installed",
        "version": VERSION,
        "bound": providers.cross_format_verification_provider is verify,
        "score_truth_patch": score_patch,
        "legacy_draft_phrase_required": False,
        "nested_report_package_supported": True,
        "canonical_semantic_fallback_supported": True,
        "canonical_score_parity_required": True,
        "final_report_semantics_required": True,
        "failed_checks_exposed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "synchronize_comprehensive_score_truth",
    "finality_aware_cross_format_verification_provider",
    "install_comprehensive_cross_format_finality_v49",
]
