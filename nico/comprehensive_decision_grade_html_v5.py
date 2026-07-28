from __future__ import annotations

import csv
import html
import io
from typing import Any, Iterable

from nico.comprehensive_decision_grade_model_v5 import _score_band, _text
from nico.comprehensive_decision_grade_markdown_v5 import _decision_summary

VERSION = "nico.comprehensive_decision_grade_html.v6"


def _escape(value: Any, limit: int = 1800) -> str:
    return html.escape(_text(value, limit))


def _html_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    head = "".join(f"<th>{_escape(item, 400)}</th>" for item in headers)
    body_rows = []
    for row in rows:
        body_rows.append("<tr>" + "".join(f"<td>{_escape(value)}</td>" for value in row) + "</tr>")
    body = "".join(body_rows) or f"<tr><td colspan='{max(1, len(headers))}'>No retained records.</td></tr>"
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _list_html(values: Iterable[Any], fallback: str = "None retained", *, limit: int = 30) -> str:
    items = []
    for value in list(values)[:limit]:
        text = _text(value, 1800)
        if text:
            items.append(f"<li>{html.escape(text)}</li>")
    return "<ul>" + ("".join(items) or f"<li>{html.escape(fallback)}</li>") + "</ul>"


def _score_rows(sections: list[dict[str, Any]]) -> list[list[Any]]:
    rows = []
    for item in sections:
        score = item.get("score_value")
        rows.append([
            item.get("label"),
            f"{score}/100" if isinstance(score, int) else "NOT SCORED",
            item.get("score_band_label"),
            item.get("assurance_label"),
            item.get("summary"),
        ])
    return rows


def _risk_rows(executive: list[dict[str, Any]]) -> list[list[Any]]:
    rows = []
    for item in executive:
        rows.append([
            item.get("priority"),
            item.get("finding_id") or item.get("id"),
            item.get("executive_title") or item.get("title"),
            item.get("business_impact") or item.get("impact"),
            item.get("canonical_location") or item.get("location"),
            item.get("recommendation"),
        ])
    return rows


def _finding_card(item: dict[str, Any]) -> str:
    title = item.get("executive_title") or item.get("title")
    finding_id = item.get("finding_id") or item.get("id")
    location = item.get("canonical_location") or item.get("location")
    related = item.get("related_locations") or []
    analyzer = item.get("analyzer_message") or item.get("interpretation") or item.get("title")
    acceptance = item.get("acceptance_criteria") or []
    roadmap = ", ".join(item.get("roadmap_mappings") or []) or "Not mapped"
    backlog = ", ".join(item.get("backlog_mappings") or []) or item.get("backlog_issue_mapping") or "Not mapped"
    return (
        f"<article class='finding'><h3>{_escape(item.get('priority'))} · {_escape(title)} "
        f"<span class='id'>{_escape(finding_id)}</span></h3>"
        f"<dl><dt>Category / status</dt><dd>{_escape(item.get('category'))} · {_escape(item.get('status') or 'open')}</dd>"
        f"<dt>Canonical location</dt><dd>{_escape(location)}</dd>"
        f"<dt>Related locations</dt><dd>{_escape(', '.join(str(value) for value in related) or location)}</dd>"
        f"<dt>Layer 1 — Evidence / fact</dt><dd>{_escape(item.get('fact') or item.get('evidence'))}</dd>"
        f"<dt>Technical summary</dt><dd>{_escape(item.get('technical_summary') or item.get('interpretation') or title)}</dd>"
        f"<dt>Original analyzer message</dt><dd>{_escape(analyzer, 2600)}</dd>"
        f"<dt>Business impact</dt><dd>{_escape(item.get('business_impact') or item.get('impact'))}</dd>"
        f"<dt>Recommendation</dt><dd>{_escape(item.get('recommendation'))}</dd>"
        f"<dt>Owner / effort</dt><dd>{_escape(item.get('owner_role'))} · {_escape(item.get('effort'))}</dd>"
        f"<dt>Residual risk</dt><dd>{_escape(item.get('residual_risk') or 'Requires review')}</dd>"
        f"<dt>Acceptance criteria</dt><dd>{_list_html(acceptance, 'Binary criterion required')}</dd>"
        f"<dt>Roadmap / backlog</dt><dd>{_escape(roadmap)} · {_escape(backlog)}</dd></dl></article>"
    )


def _finding_cards(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "<p>No actionable technical finding was retained; human review remains required.</p>"
    return "".join(_finding_card(item) for item in findings)


def _disposition_rows(assessment: dict[str, Any]) -> list[list[Any]]:
    rows = []
    for item in assessment.get("finding_dispositions") or []:
        if not isinstance(item, dict):
            continue
        disposition = item.get("disposition") if isinstance(item.get("disposition"), dict) else {}
        rows.append([
            item.get("tool"),
            item.get("rule_id"),
            item.get("canonical_location") or item.get("location"),
            disposition.get("classification"),
            disposition.get("rationale"),
        ])
    return rows


def _roadmap_html(roadmap: list[dict[str, Any]]) -> str:
    blocks = []
    for window in roadmap:
        if not isinstance(window, dict):
            continue
        packages = []
        for package in window.get("work_packages") or []:
            if not isinstance(package, dict):
                continue
            packages.append(
                f"<article class='work'><h4>{_escape(package.get('work_package_id'))} · {_escape(package.get('title'))}</h4>"
                f"<p><b>Owner:</b> {_escape(package.get('owner_role'))} · <b>Effort:</b> {_escape(package.get('effort') or package.get('effort_range'))}</p>"
                f"<p><b>Related risks:</b> {_escape(', '.join(package.get('related_finding_ids') or []) or 'None retained')}</p>"
                f"<p>{_escape(package.get('objective'))}</p>"
                f"<p><b>Acceptance:</b> {_escape('; '.join(package.get('acceptance_criteria') or []), 2600)}</p>"
                f"<p><b>Expected impact:</b> {_escape(package.get('expected_impact'))}</p></article>"
            )
        blocks.append(f"<section><h3>{_escape(window.get('window'))} — {_escape(window.get('objective'))}</h3>{''.join(packages)}</section>")
    return "".join(blocks) or "<p>No roadmap work package was retained.</p>"


def _stage_html(stages: list[dict[str, Any]]) -> str:
    blocks = []
    for index, stage in enumerate(stages, start=1):
        blocks.append(
            f"<section><h3>A{index}. {_escape(stage.get('title'))} — {_escape(str(stage.get('status') or '').upper())}</h3>"
            f"<p>{_escape(stage.get('summary'))}</p>"
            f"<p>Evidence records: {len(stage.get('evidence') or [])}; findings: {len(stage.get('findings') or [])}; limitations: {len(stage.get('unavailable') or [])}.</p>"
            f"{_list_html(stage.get('evidence') or [], 'No additional evidence item retained', limit=8)}</section>"
        )
    return "".join(blocks)


def _styles() -> str:
    return """
:root{color-scheme:dark}body{margin:0;background:#071124;color:#dbeafe;font:16px/1.55 Inter,system-ui,sans-serif}
main{max-width:1180px;margin:auto;padding:32px 20px 80px}header,section,article{border:1px solid #29405e;background:#0b172c;border-radius:18px;padding:22px;margin:16px 0}
h1{font-size:clamp(28px,5vw,48px);margin:.2em 0}h2{color:#7dd3fc;border-top:1px solid #29405e;padding-top:26px;margin-top:38px}h3{color:#e0f2fe}.id{font-size:.72em;color:#94a3b8}
p,li,dd{color:#cbd5e1}.badge{display:inline-block;padding:7px 11px;border-radius:999px;border:1px solid #f59e0b;background:#422006;color:#fde68a;font-weight:800}
.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13px}th,td{border:1px solid #334155;padding:8px;vertical-align:top;min-width:90px}th{background:#0c4a6e;color:white;text-align:left}tr:nth-child(even){background:#0f1e35}
dl{display:grid;grid-template-columns:minmax(150px,220px) 1fr;gap:7px 14px}dt{font-weight:800;color:#7dd3fc}dd{margin:0}.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.flow span{padding:12px;border:1px solid #38bdf8;border-radius:12px;background:#0c2a43}.flow b{color:#7dd3fc}.warning{border-color:#f59e0b;background:#422006;color:#fde68a;font-weight:800}
@media(max-width:760px){dl{grid-template-columns:1fr}main{padding:16px 10px 48px}header,section,article{padding:16px}}
"""


def _build_html(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
) -> str:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    adjusted = assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score"))
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
    findings = [item for item in (assessment.get("decision_grade_findings_register") or assessment.get("findings_register") or []) if isinstance(item, dict)]
    executive = [item for item in assessment.get("executive_risk_register") or [] if isinstance(item, dict)][:7]
    health = assessment.get("evidence_health_summary") if isinstance(assessment.get("evidence_health_summary"), dict) else {}
    incomplete = [item for item in health.get("incomplete_scanners") or [] if isinstance(item, dict)]
    postures = assessment.get("decision_postures") if isinstance(assessment.get("decision_postures"), dict) else {}
    title = f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
    dashboard = [
        ["Technical maturity", f"{maturity.get('score_band_label') or _score_band(score)['score_band_label']} · {int(score)}/100" if isinstance(score, (int, float)) else "NOT SCORED", "Score-derived engineering health"],
        ["Evidence-Adjusted", f"{int(adjusted)}/100" if isinstance(adjusted, (int, float)) else "NOT SCORED", "Evidence completeness constrains the technical signal"],
        ["Operate", (postures.get("operate") or {}).get("status") or "Conditional", "; ".join((postures.get("operate") or {}).get("conditions") or [])],
        ["Release", (postures.get("release") or {}).get("status") or "Conditional", "; ".join((postures.get("release") or {}).get("conditions") or [])],
        ["Client delivery", assessment.get("delivery_status") or "Human Review Required", (postures.get("client_delivery") or {}).get("required_next_action") or "Exact-package approval required"],
    ]
    incomplete_rows = [[item.get("scanner"), item.get("status"), item.get("required"), item.get("confidence_impact"), item.get("remediation")] for item in incomplete]
    disposition_rows = _disposition_rows(assessment)
    boundaries = [item for item in assessment.get("scope_boundaries") or [] if isinstance(item, dict)]
    assumptions = [item for item in assessment.get("assumption_register") or [] if isinstance(item, dict)]
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_styles()}</style></head><body><main>
<header><h1>{html.escape(title)}</h1><p>Generated {html.escape(generated_at)}</p><span class='badge'>{_escape(assessment.get('delivery_status') or 'HUMAN REVIEW REQUIRED')}</span></header>
<section><h2>Executive Decision Brief</h2><p>{_escape(_decision_summary(identity, assessment, limitations), 3500)}</p><h3>Top Priority Decisions</h3>{_list_html([f"{item.get('executive_title') or item.get('title')} [{item.get('finding_id') or item.get('id')}]" for item in executive[:3]], 'Complete exact-package review')}<p class='warning'>Client delivery is not authorized until an approved human review record exists.</p></section>
<section><h2>Assessment Coverage</h2><p>This Comprehensive assessment covers immutable repository evidence, actionable architecture and complexity, security and dependency analyzers, CI reliability, execution planning, staffing boundaries, and exact-package approval controls.</p></section>
<section><h2>Assessment Dashboard</h2>{_html_table(['Dimension','Result','Conditions / meaning'], dashboard)}</section>
<section><h2>Evidence Health Summary</h2><p>{_escape(health.get('confidence_effect') or 'Evidence remains review-gated.')}</p><p><b>Completed scanners:</b> {_escape(', '.join(health.get('completed_scanners') or []) or 'None retained')}</p>{_html_table(['Scanner','Status','Required','Confidence impact','Remediation'], incomplete_rows)}</section>
<section><h2>Canonical Technical Scorecard</h2>{_html_table(['Control','Technical score','Band','Evidence assurance','Summary'], _score_rows(sections))}</section>
<section><h2>Executive Risk Register</h2>{_html_table(['Priority','Risk ID','Decision title','Business impact','Primary location','Required action'], _risk_rows(executive))}</section>
{f"<section><h2>Source-Reviewed Analyzer Dispositions</h2><p>These records remain visible with exact-source rationale and are not silently suppressed.</p>{_html_table(['Analyzer','Rule','Source','Classification','Rationale'], disposition_rows)}</section>" if disposition_rows else ''}
<h2>Detailed Findings Register</h2>{_finding_cards(findings)}
<section><h2>Architecture and Data Flow</h2><div class='flow'><span>Repository</span><b>→</b><span>Immutable Snapshot</span><b>→</b><span>Evidence</span><b>→</b><span>Canonical Findings</span><b>→</b><span>Decision</span><b>→</b><span>Verification</span><b>→</b><span>Human Review</span></div></section>
<h2>Six-Month Execution Roadmap</h2>{_roadmap_html(roadmap)}
<section><h2>Staffing and Sequencing</h2>{_list_html([f"Sequence {item.get('sequence')}: {item.get('role')} — {item.get('focus')}" for item in staffing if isinstance(item, dict)], 'Requires stakeholder approval.')}</section>
<section><h2>How to Use This Report</h2>{_list_html(assessment.get('how_to_use_report') or [], 'Complete exact-package human review before delivery.')}</section>
<section><h2>Scope Boundary and Unassessed Risk</h2>{_html_table(['Area','Boundary'], [[item.get('area'), item.get('boundary')] for item in boundaries] or [['Unassessed domains','Must not be interpreted as healthy']])}</section>
<section><h2>Assumption Register</h2>{_html_table(['ID','Category','Assumption','Source','Confidence','Sensitivity','Consequence if wrong'], [[item.get('assumption_id'),item.get('category'),item.get('description'),item.get('source'),item.get('confidence'),item.get('sensitivity'),item.get('consequence_if_wrong')] for item in assumptions] or [['—','—','No structured assumption retained','—','—','—','Human validation required']])}</section>
<h2>Evidence Appendix</h2>{_stage_html(stages)}
<section><h2>Human Review and Acceptance Gate</h2>{_list_html(['Verify exact identities and immutable evidence.', 'Triage every material, review-required, failed, timed-out, and unavailable analyzer result.', 'Confirm cross-format score, scanner, finding, limitation, CI, and delivery truth.', 'Approve or reject the exact immutable package.'])}<p class='warning'>{_escape(assessment.get('delivery_status') or 'HUMAN REVIEW REQUIRED')} — CLIENT DELIVERY NOT AUTHORIZED WITHOUT EXACT-PACKAGE APPROVAL</p></section>
</main></body></html>"""


def _csv_cell(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return "; ".join(_text(item, 3000) for item in value)
    if isinstance(value, dict):
        import json
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _text(value, 6000)


def _findings_csv(findings: list[dict[str, Any]]) -> str:
    fields = [
        "id", "priority", "category", "executive_title", "technical_summary",
        "analyzer_message", "canonical_path", "canonical_line", "canonical_location",
        "related_locations", "finding_id", "fact", "evidence", "business_impact",
        "confidence", "owner_role", "effort", "recommendation", "acceptance_criteria",
        "cost_of_inaction", "residual_risk", "roadmap_mappings", "backlog_mappings",
        "backlog_issue_mapping", "status", "source_evidence_fingerprint",
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in findings:
        if isinstance(item, dict):
            writer.writerow({field: _csv_cell(item.get(field)) for field in fields})
    return stream.getvalue()


def _evidence_csv(stages: list[dict[str, Any]]) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["stage_id", "stage_title", "stage_status", "record_type", "record"])
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        for record_type in ("evidence", "findings", "unavailable"):
            for item in stage.get(record_type) or []:
                writer.writerow([
                    stage.get("stage_id"), stage.get("title"), stage.get("status"),
                    record_type, _csv_cell(item),
                ])
    return stream.getvalue()


__all__ = ["VERSION", "_build_html", "_findings_csv", "_evidence_csv"]
