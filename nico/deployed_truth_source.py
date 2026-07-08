from __future__ import annotations

import json
import re
from typing import Any

import requests

OSV_API = "https://api.osv.dev/v1/querybatch"
MALFORMED_OSV_RE = re.compile(
    r"OSV returned\s+\d+\s+vulnerability record\(s\)\s+for\s+[^:\n]+:[^\s\n]+@\[[^\]]+\][^:\n]*:?[^\n]*",
    re.IGNORECASE,
)


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value)
    return str(value or "")


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in result.get("sections", []) or []
            if isinstance(item, dict) and item.get("id") == section_id
        ),
        None,
    )


def _section_text(section: dict[str, Any] | None) -> str:
    if not section:
        return ""
    return "\n".join(_text(section.get(key)) for key in ("summary", "evidence", "findings", "unavailable"))


def _status_from_score(score: int) -> str:
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def normalize_requirement_name(raw_name: str) -> str:
    return re.sub(r"\[[^\]]+\]", "", str(raw_name or "")).strip()


def parse_requirements_normalized(text: str) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(
            r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*(==|~=|>=|<=|>|<)?\s*([^;#\s]+)?",
            line,
        )
        if not match:
            continue
        name, operator, version = match.groups()
        deps.append(
            {
                "name": normalize_requirement_name(name),
                "operator": operator or "",
                "version": str(version or "").strip(),
                "ecosystem": "PyPI",
                "source": "requirements.txt",
            }
        )
    return deps


def exact_osv_dependencies(dependencies: list[dict[str, Any]]) -> list[dict[str, str]]:
    exact: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for dep in dependencies:
        name = normalize_requirement_name(str(dep.get("name") or ""))
        version = str(dep.get("version") or "").strip()
        operator = str(dep.get("operator") or "").strip()
        ecosystem = str(dep.get("ecosystem") or "").strip() or "PyPI"
        if operator and operator != "==":
            continue
        if not name or not version or version in {"*", "latest"}:
            continue
        if version.startswith("[") or any(marker in version for marker in ["[", "]", " ", ">", "<", "="]):
            continue
        key = (ecosystem, name, version)
        if key not in seen:
            seen.add(key)
            exact.append({"name": name, "version": version, "ecosystem": ecosystem})
    return exact


def query_osv_exact(dependencies: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    pinned = exact_osv_dependencies(dependencies)[:75]
    if not pinned:
        return [], ["OSV lookup skipped because no exact normalized dependency versions were available from the inspected manifests."]
    queries = [
        {"package": {"name": dep["name"], "ecosystem": dep["ecosystem"]}, "version": dep["version"]}
        for dep in pinned
    ]
    try:
        response = requests.post(OSV_API, json={"queries": queries}, timeout=20)
    except requests.RequestException as exc:
        return [], [f"OSV lookup unavailable: {exc}"]
    if response.status_code >= 400:
        return [], [f"OSV lookup returned HTTP {response.status_code}; dependency vulnerability status is incomplete."]
    try:
        data = response.json()
    except ValueError:
        return [], ["OSV lookup returned a non-JSON response."]
    evidence: list[str] = []
    results = data.get("results", []) if isinstance(data, dict) else []
    for dep, result in zip(pinned, results):
        vulns = result.get("vulns", []) if isinstance(result, dict) else []
        if vulns:
            ids = ", ".join(str(v.get("id")) for v in vulns[:5] if isinstance(v, dict))
            evidence.append(f"OSV returned {len(vulns)} vulnerability record(s) for {dep['ecosystem']}:{dep['name']}@{dep['version']}: {ids}.")
    if not evidence:
        evidence.append(f"OSV returned no vulnerability records for {len(pinned)} exact normalized dependency query/queries.")
    return evidence, []


def _has_real_osv_vulnerability(section: dict[str, Any] | None) -> bool:
    text = _section_text(section).lower()
    if not ("osv returned" in text and "vulnerability record" in text):
        return False
    if "no vulnerability records" in text:
        return False
    real_lines = [line for line in text.splitlines() if "osv returned" in line and "vulnerability record" in line and "@[" not in line]
    return bool(real_lines)


def _has_malformed_osv_query(section: dict[str, Any] | None) -> bool:
    return bool(section and "@[" in _section_text(section) and "osv returned" in _section_text(section).lower())


def _remove_malformed_osv_lines(items: list[Any]) -> list[Any]:
    kept: list[Any] = []
    for item in items:
        text = str(item or "")
        if "osv returned" in text.lower() and "@[" in text:
            continue
        if "osv api completed_with_findings" in text.lower() and "@[" in text:
            continue
        kept.append(item)
    return kept


def _recompute_maturity(result: dict[str, Any]) -> None:
    sections = [
        item
        for item in result.get("sections", []) or []
        if isinstance(item, dict)
        and item.get("status") != "gray"
        and item.get("supplemental") is not True
        and int(item.get("scoring_weight", 1) or 0) != 0
    ]
    if not sections:
        return
    score = round(sum(int(item.get("score") or 0) for item in sections) / len(sections))
    level = "Senior" if score >= 82 else ("Mid" if score >= 58 else "Junior")
    summary = (
        "Evidence suggests mature delivery foundations with documented structure, automation, and low-risk signals, pending human validation."
        if score >= 82
        else "Evidence suggests useful foundations exist, but operating maturity depends on closing traceability, test, dependency, or automation gaps."
        if score >= 58
        else "Evidence suggests early-stage maturity or missing access to the signals needed for confident assessment."
    )
    result["maturity_signal"] = {"level": level, "score": score, "summary": summary}
    result["maturity_semaphore"] = {item.get("label", item.get("id", "Section")): item.get("status") for item in sections}
    result["maturity_semaphore"]["Work vs Expected"] = level
    result["executive_summary"] = (
        f"NICO completed an authorized hosted Express Technical Health Assessment for {result.get('repository', 'the authorized repository')}. "
        f"The final maturity signal is {level} ({score}/100). Scores are generated from the final evidence-bound result after code audit, dependency, secrets, static analysis, CI/CD, architecture, velocity, artifact evidence, retained project history when available, acceptance when approved, and explicit unavailable-data notes have been applied. Final delivery still requires human review."
    )
    result["score_source_of_truth"] = {"field": "maturity_signal", "score": score, "level": level}


def _rebuild_reports(result: dict[str, Any]) -> None:
    from nico.hosted_assessment import build_html, build_markdown, build_pdf_base64

    markdown = build_markdown(result)
    html = build_html(markdown)
    pdf_base64, pdf_error = build_pdf_base64(markdown)
    reports = {"markdown": markdown, "html": html}
    if pdf_base64:
        reports["pdf_base64"] = pdf_base64
    if pdf_error:
        result.setdefault("unavailable_data_notes", [])
        _append_unique(result["unavailable_data_notes"], pdf_error)
    result["reports"] = reports


def apply_deployed_truth_invariants(result: dict[str, Any]) -> dict[str, Any]:
    dependency = _section(result, "dependency_health")
    if dependency:
        dependency.setdefault("evidence", [])
        dependency.setdefault("findings", [])
        dependency.setdefault("unavailable", [])
        malformed_osv = _has_malformed_osv_query(dependency)
        if malformed_osv:
            dependency["evidence"] = _remove_malformed_osv_lines(dependency.get("evidence", []) or [])
            dependency["findings"] = _remove_malformed_osv_lines(dependency.get("findings", []) or [])
            _append_unique(
                dependency["findings"],
                "Malformed OSV dependency evidence was discarded: Python extras were present in the OSV version field. Rerun normalized OSV lookup before treating that item as a vulnerability finding.",
            )
            _append_unique(
                dependency["unavailable"],
                "Normalized current-run OSV evidence is required because a malformed extras-based OSV query was detected and ignored.",
            )
            dependency["score"] = min(int(dependency.get("score") or 0), 86)
            dependency["summary"] = "Dependency review has manifest and lockfile evidence, but malformed OSV extras evidence was discarded; final scanner-clean dependency status is not claimed without normalized current-run audit artifacts."
        if _has_real_osv_vulnerability(dependency):
            dependency["score"] = min(int(dependency.get("score") or 0), 74)
            dependency["summary"] = "Dependency review found OSV vulnerability records from normalized dependency evidence; final scanner-clean status is not claimed until current-run audit artifacts prove resolution or non-applicability."
            _append_unique(
                dependency["findings"],
                "Dependency score consistency guard: normalized OSV vulnerability records are present, so this section cannot claim GREEN 90 until current-run pip-audit, npm audit, and OSV Scanner artifacts prove resolution or non-applicability.",
            )
        dependency["status"] = _status_from_score(int(dependency.get("score") or 0))
    _recompute_maturity(result)
    _rebuild_reports(result)
    return result


def install_deployed_truth_source() -> None:
    from nico import hosted_assessment
    from nico import final_report_consistency

    hosted_assessment.parse_requirements = parse_requirements_normalized
    hosted_assessment.query_osv = query_osv_exact

    original_finalize = getattr(final_report_consistency, "_nico_deployed_truth_original_finalize", None)
    if original_finalize is None:
        original_finalize = final_report_consistency.finalize_express_result_consistency
        final_report_consistency._nico_deployed_truth_original_finalize = original_finalize

    def finalize_with_deployed_truth(result: dict[str, Any]) -> dict[str, Any]:
        finalized = original_finalize(result)
        if finalized.get("status") == "complete":
            return apply_deployed_truth_invariants(finalized)
        return finalized

    final_report_consistency.finalize_express_result_consistency = finalize_with_deployed_truth
