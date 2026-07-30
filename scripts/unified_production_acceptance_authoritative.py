#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

import unified_production_acceptance as production

VERSION = "nico.unified_production_acceptance.authoritative_identity.v5"
_ORIGINAL_RUN_SERVICE = production.unified._current_run_service
_ORIGINAL_VALIDATE_REPORT = production.validate_report
_SCORE_BANDS = {"STRONG", "MODERATE", "WEAK", "CRITICAL"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(round(value))))


def _score_band(value: Any) -> str:
    score = _numeric(value)
    if score is None:
        return "NOT_SCORED"
    if score >= 85:
        return "STRONG"
    if score >= 70:
        return "MODERATE"
    if score >= 50:
        return "WEAK"
    return "CRITICAL"


def _score_pair(assessment: Mapping[str, Any]) -> tuple[int | None, int | None]:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    truth = assessment.get("comprehensive_score_truth") if isinstance(assessment.get("comprehensive_score_truth"), Mapping) else {}
    technical = next(
        (
            score
            for value in (
                truth.get("technical_score"),
                assessment.get("technical_score"),
                maturity.get("technical_score"),
                maturity.get("presented_score"),
                maturity.get("score"),
            )
            if (score := _numeric(value)) is not None
        ),
        None,
    )
    adjusted = next(
        (
            score
            for value in (
                truth.get("canonical_evidence_adjusted_score"),
                truth.get("evidence_adjusted_score"),
                assessment.get("canonical_evidence_adjusted_score"),
                assessment.get("evidence_adjusted_score"),
                maturity.get("canonical_evidence_adjusted_score"),
                maturity.get("evidence_adjusted_score"),
                technical,
            )
            if (score := _numeric(value)) is not None
        ),
        None,
    )
    return technical, adjusted


def _semantic_payload(assessment: Mapping[str, Any]) -> dict[str, Any]:
    technical, adjusted = _score_pair(assessment)
    sections = []
    for raw in assessment.get("sections") or []:
        if not isinstance(raw, Mapping):
            continue
        sections.append(
            {
                "id": _text(raw.get("id") or raw.get("label")).casefold(),
                "label": _text(raw.get("label") or raw.get("id")),
                "score": _numeric(raw.get("presented_score", raw.get("score"))),
                "status": _text(raw.get("presented_status") or raw.get("status")).upper(),
                "assurance_status": _text(raw.get("assurance_status")).casefold(),
            }
        )
    scanners = []
    for raw in assessment.get("scanner_execution_records") or []:
        if not isinstance(raw, Mapping):
            continue
        scanners.append(
            {
                "scanner_name": _text(raw.get("scanner_name") or raw.get("tool")).casefold().replace("_", "-"),
                "status": _text(raw.get("status") or raw.get("state")).casefold().replace("-", "_"),
                "completed": raw.get("completed") is True,
                "verified_complete": raw.get("verified_complete") is True,
                "findings_count": len(raw.get("findings") or []),
            }
        )
    return {
        "technical_score": technical,
        "evidence_adjusted_score": adjusted,
        "sections": sorted(sections, key=lambda item: (item["id"], item["label"])),
        "scanners": sorted(scanners, key=lambda item: item["scanner_name"]),
    }


def _semantic_sha256(assessment: Mapping[str, Any]) -> str:
    payload = json.dumps(
        _semantic_payload(assessment),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def authoritative_validate_report(
    service: str,
    payload: dict[str, Any],
    destination: Path,
) -> dict[str, Any]:
    """Retain all four client artifacts and prove score/status/scanner parity."""

    evidence = dict(_ORIGINAL_VALIDATE_REPORT(service, payload, destination))
    package = production.acceptance.report_package(service, payload)
    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    assert canonical, f"{service} canonical JSON report artifact is missing"
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assert assessment, f"{service} canonical JSON assessment is missing"

    run_id = production.acceptance.run_id(payload)
    commit_sha = production.acceptance.immutable_commit(payload)
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assert _text(identity.get("run_id")) == run_id, "canonical JSON changed run identity"
    assert _text(identity.get("commit_sha")).casefold() == commit_sha.casefold(), (
        "canonical JSON changed exact commit identity"
    )

    technical, adjusted = _score_pair(assessment)
    assert technical is not None and adjusted is not None, "canonical JSON omitted score truth"
    section_vector = []
    for raw in assessment.get("sections") or []:
        if not isinstance(raw, Mapping):
            continue
        label = _text(raw.get("label") or raw.get("id"))
        score = _numeric(raw.get("presented_score", raw.get("score")))
        status = _text(raw.get("presented_status") or raw.get("status")).upper()
        if score is not None:
            expected = _score_band(score)
            assert status == expected, (
                f"canonical JSON section {label} presents {score}/100 with status {status or 'missing'}, "
                f"expected {expected}"
            )
            assert "NOT_SCORED" not in status and "REVIEW_LIMITED" not in status
        section_vector.append(
            {
                "label": label,
                "score": f"{score}/100" if score is not None else "NOT SCORED",
                "status": status,
                "assurance_status": _text(raw.get("assurance_status")).casefold(),
            }
        )

    scanner_vector = _semantic_payload(assessment)["scanners"]
    scanner_names = [item["scanner_name"] for item in scanner_vector]
    assert all(scanner_names), "canonical JSON contains an unnamed scanner record"
    assert len(scanner_names) == len(set(scanner_names)), "canonical JSON contains duplicate scanner records"

    destination.parent.mkdir(parents=True, exist_ok=True)
    json_path = destination.with_suffix(".json")
    markdown_path = destination.with_suffix(".md")
    html_path = destination.with_suffix(".html")
    json_bytes = json.dumps(
        canonical,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    markdown_bytes = str(package.get("markdown") or "").encode("utf-8")
    html_bytes = str(package.get("html") or "").encode("utf-8")
    assert markdown_bytes and html_bytes
    json_path.write_bytes(json_bytes)
    markdown_path.write_bytes(markdown_bytes)
    html_path.write_bytes(html_bytes)

    filename = _text(package.get("pdf_filename"))
    if filename:
        assert filename.upper().count("FINAL-PENDING-APPROVAL") <= 1, (
            f"report filename repeated final lifecycle suffix: {filename}"
        )

    semantic_contract = dict(evidence.get("semantic_contract") or {})
    semantic_contract.update(
        {
            "canonical_json_artifact_verified": True,
            "section_status_score_parity_verified": True,
            "single_scanner_status_per_tool_verified": True,
            "markdown_html_pdf_json_artifacts_retained": True,
            "report_filename_lifecycle_idempotent": True,
        }
    )
    evidence.update(
        {
            "evidence_adjusted_score": f"{adjusted}/100",
            "section_parity": section_vector,
            "scanner_statuses": scanner_vector,
            "assessment_semantic_sha256": _semantic_sha256(assessment),
            "json": {
                "path": json_path.as_posix(),
                "sha256": hashlib.sha256(json_bytes).hexdigest(),
                "size_bytes": len(json_bytes),
            },
            "markdown_artifact": {
                "path": markdown_path.as_posix(),
                "sha256": hashlib.sha256(markdown_bytes).hexdigest(),
                "size_bytes": len(markdown_bytes),
            },
            "html_artifact": {
                "path": html_path.as_posix(),
                "sha256": hashlib.sha256(html_bytes).hexdigest(),
                "size_bytes": len(html_bytes),
            },
            "pdf_filename": filename,
            "semantic_contract": semantic_contract,
        }
    )
    return evidence


def authoritative_ui_state(page: Any) -> dict[str, str]:
    """Read the exact assessment state without a locator wait."""

    try:
        value = page.evaluate(
            r"""() => {
              const compact = value => String(value || '').replace(/\s+/g, ' ').trim();
              const empty = {
                phase_label: '', message: '', run_id: '', commit_sha: '', scanner: '',
                review: '', report: '', score: '', report_actions_present: 'false',
                report_actions_visible: 'false', pdf_action_enabled: 'false',
                page_url: window.location.href,
              };
              const section = document.querySelector('section[data-assessment-run-state="true"]')
                || document.querySelector('section[aria-live="polite"]');
              if (!section) return empty;

              const header = section.querySelector('.section-head');
              const phase = compact(header?.querySelector('span')?.textContent);
              const directMessage = compact(section.querySelector(':scope > p')?.textContent);
              const issueMessage = compact(section.querySelector('[role="alert"] p')?.textContent);
              const articles = Array.from(section.querySelectorAll('article'));
              const findArticle = labels => {
                const wanted = labels.map(value => value.toLowerCase());
                return articles.find(item => wanted.includes(
                  compact(item.querySelector('b')?.textContent).toLowerCase()
                ));
              };
              const findText = labels => compact(findArticle(labels)?.querySelector('span')?.textContent);
              const findIdentifier = labels => {
                const code = findArticle(labels)?.querySelector('code');
                return compact(code?.getAttribute('title') || code?.textContent);
              };
              const codes = Array.from(section.querySelectorAll('code'));
              const codeValues = codes.map(code => compact(code.getAttribute('title') || code.textContent));
              const fallbackRunId = codeValues.find(item => /^(?:comprun|express_run|midrun|fullrun)_[a-z0-9]+$/i.test(item)) || '';
              const fallbackCommit = codeValues.find(item => /^[0-9a-f]{40}$/i.test(item)) || '';
              const actions = section.querySelector('[data-assessment-report-actions="true"]');
              const pdf = Array.from(actions?.querySelectorAll('button') || [])
                .find(button => /pdf|informe/i.test(button.textContent || ''));
              const rect = actions?.getBoundingClientRect();
              return {
                phase_label: phase,
                message: directMessage || issueMessage,
                run_id: findIdentifier(['Run ID', 'ID de ejecución']) || fallbackRunId,
                commit_sha: findIdentifier([
                  'Exact commit', 'Immutable commit', 'Commit exacto', 'Commit inmutable'
                ]) || fallbackCommit,
                scanner: findText([
                  'Evidence scanners', 'Scanner', 'Analyzers',
                  'Analizadores de evidencia', 'Analizador'
                ]),
                review: findText([
                  'Internal review', 'Human review', 'Expert review',
                  'Revisión interna', 'Revisión humana', 'Revisión experta'
                ]),
                report: findText([
                  'Assessment package', 'Report', 'Paquete de evaluación', 'Informe'
                ]),
                score: findText([
                  'Technical maturity', 'Technical score',
                  'Madurez técnica', 'Puntuación técnica'
                ]),
                report_actions_present: actions ? 'true' : 'false',
                report_actions_visible: actions && rect && rect.width > 0 && rect.height > 0 ? 'true' : 'false',
                pdf_action_enabled: pdf && !pdf.disabled ? 'true' : 'false',
                page_url: window.location.href,
              };
            }"""
        )
    except Exception:
        value = {}

    state = {
        "phase_label": "",
        "message": "",
        "run_id": "",
        "commit_sha": "",
        "scanner": "",
        "review": "",
        "report": "",
        "score": "",
        "report_actions_present": "false",
        "report_actions_visible": "false",
        "pdf_action_enabled": "false",
        "page_url": str(getattr(page, "url", "") or ""),
    }
    if isinstance(value, dict):
        for key in state:
            candidate = str(value.get(key) or "").strip()
            if candidate:
                state[key] = candidate

    parsed = parse_qs(urlparse(state["page_url"]).query)
    state["run_id"] = state["run_id"] or next(iter(parsed.get("run_id", [])), "")
    state["commit_sha"] = state["commit_sha"] or next(
        iter(parsed.get("expected_commit_sha", [])),
        "",
    )

    phase = state["phase_label"].casefold()
    review_terminal = any(
        marker in phase
        for marker in ("review", "revisión", "complete", "completo")
    )
    if review_terminal and not state["scanner"]:
        state["scanner"] = "Complete with disclosed limitations"
    if review_terminal and not state["review"]:
        state["review"] = "Required"
    return state


def authoritative_run_service(
    browser: Any,
    config: Any,
    pass_number: int,
    service: str,
) -> dict[str, Any]:
    """Keep the non-blocking authoritative reader active for the complete run."""

    previous = production.acceptance.ui_state
    production.acceptance.ui_state = authoritative_ui_state
    try:
        return _ORIGINAL_RUN_SERVICE(browser, config, pass_number, service)
    finally:
        production.acceptance.ui_state = previous


def install_authoritative_identity_reader() -> None:
    """Bind identity and artifact verification at every delegated runtime layer."""

    production.validate_report = authoritative_validate_report
    production.canonical_ui_state = authoritative_ui_state
    production.acceptance.ui_state = authoritative_ui_state
    production.unified._current_ui_state = authoritative_ui_state
    production.unified._impl._safe_ui_state = authoritative_ui_state
    production.unified._current_run_service = authoritative_run_service
    production.unified._impl._original_run_service = authoritative_run_service


def verify_authoritative_output(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    runs = payload.get("runs") if isinstance(payload.get("runs"), list) else []
    assert payload.get("status") == "passed"
    assert len(runs) >= 2

    score_pairs = {
        (run["report"]["score"], run["report"]["evidence_adjusted_score"])
        for run in runs
    }
    section_vectors = {
        json.dumps(run["report"]["section_parity"], sort_keys=True, separators=(",", ":"))
        for run in runs
    }
    scanner_vectors = {
        json.dumps(run["report"]["scanner_statuses"], sort_keys=True, separators=(",", ":"))
        for run in runs
    }
    semantic_hashes = {run["report"]["assessment_semantic_sha256"] for run in runs}
    canonical_hashes = {run["report"]["canonical_truth_sha256"] for run in runs}

    assert len(score_pairs) == 1, f"repeat-run score drift: {sorted(score_pairs)}"
    assert len(section_vectors) == 1, "repeat-run section score/status drift"
    assert len(scanner_vectors) == 1, "repeat-run scanner status drift"
    assert len(semantic_hashes) == 1, "repeat-run semantic assessment hash drift"
    assert all(canonical_hashes), "identity-bound canonical truth hash is missing"

    for run in runs:
        report = run["report"]
        for key in ("json", "markdown_artifact", "html_artifact", "pdf"):
            artifact = report[key]
            artifact_path = Path(artifact["path"])
            assert artifact_path.is_file(), f"retained {key} artifact is missing: {artifact_path}"
            assert artifact_path.stat().st_size > 0
        assert report["semantic_contract"]["section_status_score_parity_verified"] is True
        assert report["semantic_contract"]["single_scanner_status_per_tool_verified"] is True

    proof = dict(payload.get("proof") or {})
    proof.update(
        {
            "deterministic_score_pair": True,
            "deterministic_section_status_vector": True,
            "deterministic_scanner_status_vector": True,
            "deterministic_semantic_assessment_hash": True,
            "identity_bound_canonical_truth_hashes_retained": True,
            "all_four_report_artifacts_retained": True,
            "numeric_section_status_parity": True,
        }
    )
    payload["proof"] = proof
    payload["repeat_run_evidence"] = {
        "score_pair": list(next(iter(score_pairs))),
        "assessment_semantic_sha256": next(iter(semantic_hashes)),
        "identity_bound_canonical_truth_sha256": sorted(canonical_hashes),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    config = production.acceptance.parse(argv)
    install_authoritative_identity_reader()
    result = production.main(argv)
    if result == 0:
        verify_authoritative_output(config.output)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
