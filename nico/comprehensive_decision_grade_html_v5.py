from __future__ import annotations

import csv
import html
import io
from typing import Any

from nico.comprehensive_decision_grade_model_v5 import _score_band, _text
from nico.comprehensive_decision_grade_markdown_v5 import _decision_summary


def _html_table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{html.escape(_text(item, 400))}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(_text(value, 1800))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _list_html(values: list[Any], fallback: str = "None retained") -> str:
    items = [f"<li>{html.escape(_text(item, 1800))}</li>" for item in values if _text(item, 1800)]
    return "<ul>" + ("".join(items) or f"<li>{html.escape(fallback)}</li>") + "</ul>"


def _build_html(identity: dict[str, Any], assessment: dict[str, Any], stages: list[dict[str, Any]], roadmap: list[dict[str, Any]], staffing: list[dict[str, Any]], limitations: dict[str, int], generated_at: str) -> str:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    adjusted = assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score"))
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
    findings = [item for item in (assessment.get("decision_grade_findings_register") or assessment.get("findings_register") or []) if isinstance(item, dict)]
    executive = [item for item in assessment.get("executive_risk_register") or [] if isinstance(item, dict)][:7]
    score_rows = [[item.get("label"), f"{item.get('score_value')}/100" if isinstance(item.get("score_value"), int) else "NOT SCORED", item.get("score_band_label"), item.get("assurance_label"), item.get("summary")] for item in sections]
    risk_rows = [[item.get("priority"), item.get("finding_id") or item.get("id"), item.get("title"), item.get("business_impact") or item.get("impact"), item.get("confidence"), item.get("recommendation"), item.get("effort"), item.get("cost_of_inaction"), item.get("residual_risk"), item.get("location")] for item in executive]
    finding_cards = "".join(
        f"<section class='finding'><h3>{html.escape(_text(item.get('priority')))} · {html.escape(_text(item.get('title')))} · {html.escape(_text(item.get('finding_id') or item.get('id')))}</h3>"
        f"<dl><dt>Category</dt><dd>{html.escape(_text(item.get('category')))}</dd><dt>Location</dt><dd>{html.escape(_text(item.get('location')))}</dd>"
        f"<dt>Layer 1 — Evidence / fact</dt><dd>{html.escape(_text(item.get('fact') or item.get('evidence')))}</dd>"
        f"<dt>Layer 2 — Interpretation</dt><dd>{html.escape(_text(item.get('interpretation') or item.get('title')))}</dd>"
        f"<dt>Layer 3 — Business inference</dt><dd>{html.escape(_text(item.get('business_impact') or item.get('impact')))}</dd>"
        f"<dt>Layer 4 — Recommendation</dt><dd>{html.escape(_text(item.get('recommendation')))}</dd>"
        f"<dt>Owner / effort</dt><dd>{html.escape(_text(item.get('owner_role')))} · {html.escape(_text(item.get('effort')))}</dd>"
        f"<dt>Cost of inaction</dt><dd>{html.escape(_text(item.get('cost_of_inaction') or 'Not quantified'))}</dd>"
        f"<dt>Residual risk</dt><dd>{html.escape(_text(item.get('residual_risk') or 'Requires review'))}</dd>"
        f"<dt>Acceptance criteria</dt><dd>{_list_html(item.get('acceptance_criteria') or [], 'Binary criterion required')}</dd>"
        f"<dt>Roadmap / backlog</dt><dd>{html.escape(_text(', '.join(item.get('roadmap_mappings') or []) or 'Not mapped'))} · {html.escape(_text(item.get('backlog_issue_mapping') or 'Not mapped'))}</dd></dl></section>"
        for item in findings
    ) or "<p>No structured technical finding was retained; human review remains required.</p>"
    roadmap_html = "".join(
        f"<section><h3>{html.escape(_text(window.get('window')))} — {html.escape(_text(window.get('objective')))}</h3>"
        + "".join(
            f"<article class='work'><h4>{html.escape(_text(package.get('work_package_id')))} · {html.escape(_text(package.get('title')))}</h4>"
            f"<p><b>Classification:</b> {html.escape(_text(package.get('classification')))} · <b>Owner:</b> {html.escape(_text(package.get('owner_role')))} · <b>Effort:</b> {html.escape(_text(package.get('effort') or package.get('effort_range')))}</p>"
            f"<p><b>Related risks:</b> {html.escape(_text(', '.join(package.get('related_finding_ids') or []) or 'None retained'))}</p>"
            f"<p>{html.escape(_text(package.get('objective')))}</p><p><b>Sequence:</b> {html.escape(_text('; '.join(package.get('ordered_implementation_steps') or [])))}</p>"
            f"<p><b>Acceptance:</b> {html.escape(_text('; '.join(package.get('acceptance_criteria') or [])))}</p>"
            f"<p><b>Expected impact:</b> {html.escape(_text(package.get('expected_impact')))}</p><p><b>Residual risk:</b> {html.escape(_text(package.get('residual_risk')))}</p></article>"
            for package in window.get("work_packages") or []
            if isinstance(package, dict)
        )
        + "</section>"
        for window in roadmap
        if isinstance(window, dict)
    )
    stage_html = "".join(
        f"<section><h3>A{index}. {html.escape(stage['title'])} — {html.escape(stage['status'].upper())}</h3><p>{html.escape(stage['summary'])}</p>"
        f"<p>Evidence records: {len(stage.get('evidence') or [])}; findings: {len(stage.get('findings') or [])}; limitations: {len(stage.get('unavailable') or [])}.</p>"
        + ("<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in (stage.get("evidence") or [])[:8]) + "</ul>" if stage.get("evidence") else "")
        + "</section>"
        for index, stage in enumerate(stages, start=1)
    )
    health = assessment.get("evidence_health_summary") if isinstance(assessment.get("evidence_health_summary"), dict) else {}
    incomplete_rows = [[item.get("scanner"), item.get("status"), item.get("required"), ", ".join(item.get("affected_categories") or []), item.get("confidence_impact"), item.get("remediation")] for item in health.get("incomplete_scanners") or [] if isinstance(item, dict)]
    boundaries = [item for item in assessment.get("scope_boundaries") or [] if isinstance(item, dict)]
    assumptions = [item for item in assessment.get("assumption_register") or [] if isinstance(item, dict)]
    postures = assessment.get("decision_postures") if isinstance(assessment.get("decision_postures"), dict) else {}
    title = f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>
:root{{color-scheme:dark}}body{{margin:0;background:#071124;color:#dbeafe;font:16px/1.55 Inter,system-ui,sans-serif}}main{{max-width:1400px;margin:auto;padding:32px 20px 80px}}header,section,article{{border:1px solid #29405e;background:#0b172c;border-radius:18px;padding:22px;margin:16px 0}}h1{{font-size:clamp(28px,5vw,48px);margin:.2em 0}}h2{{color:#7dd3fc;border-top:1px solid #29405e;padding-top:26px;margin-top:38px}}h3{{color:#e0f2fe}}p,li,dd{{color:#cbd5e1}}.badge{{display:inline-block;padding:7px 11px;border-radius:999px;border:1px solid #f59e0b;background:#422006;color:#fde68a;font-weight:800}}table{{width:100%;border-collapse:collapse;margin:14px 0;font-size:13px}}th,td{{border:1px solid #334155;padding:8px;vertical-align:top}}th{{background:#0c4a6e;color:white;text-align:left;position:sticky;top:0}}tr:nth-child(even){{background:#0f1e35}}dl{{display:grid;grid-template-columns:minmax(150px,220px) 1fr;gap:7px 14px}}dt{{font-weight:800;color:#7dd3fc}}dd{{margin:0}}.flow{{display:flex;flex-wrap:wrap;gap:8px;align-items:center}}.flow span{{padding:12px;border:1px solid #38bdf8;border-radius:12px;background:#0c2a43}}.flow b{{color:#7dd3fc}}.warning{{border-color:#f59e0b;background:#422006;color:#fde68a;font-weight:800}}.wide{{overflow-x:auto}}@media(max-width:760px){{table{{display:block;overflow-x:auto}}dl{{grid-template-columns:1fr}}}}
</style></head><body><main><header><h1>{html.escape(title)}</h1><p>Generated {html.escape(generated_at)}</p><span class='badge'>{html.escape(_text(assessment.get('delivery_status') or 'HUMAN REVIEW REQUIRED'))}</span></header>
<section><h2>Executive Decision Brief</h2><p>{html.escape(_decision_summary(identity, assessment, limitations))}</p><h3>Top Priority Decisions</h3>{_list_html([f"{item.get('title')} [{item.get('finding_id') or item.get('id')}]" for item in executive[:3]], 'Complete exact-package review')}<p class='warning'>Client delivery is not authorized until an approved human review record exists.</p></section>
<section><h2>Assessment Dashboard</h2>{_html_table(['Dimension','Result','Conditions / meaning'], [['Technical maturity', f"{maturity.get('score_band_label') or _score_band(score)['score_band_label']} · {int(score)}/100" if isinstance(score,(int,float)) else 'NOT SCORED','Score-derived engineering health'],['Evidence-Adjusted',f'{int(adjusted)}/100' if isinstance(adjusted,(int,float)) else 'NOT SCORED','Evidence completeness constrains the technical signal'],['Operate',(postures.get('operate') or {}).get('status') or 'Conditional','; '.join((postures.get('operate') or {}).get('conditions') or [])],['Release',(postures.get('release') or {}).get('status') or 'Conditional','; '.join((postures.get('release') or {}).get('conditions') or [])],['Client delivery',assessment.get('delivery_status') or 'Human Review Required',(postures.get('client_delivery') or {}).get('required_next_action') or 'Exact-package approval required']])}</section>
<section><h2>Limitation Accounting</h2>{_html_table(['Metric','Count','Definition'], [['Stages with limitations',limitations['stages_with_limitations'],'Stages with at least one limitation'],['Distinct limitation records',limitations['individual_limitation_records'],'Deduplicated records'],['Score-affecting records',limitations['score_affecting_records'],'Section findings or gaps'],['Informational records',limitations['informational_records'],'Non-score disclosures']])}</section>
<section><h2>Evidence Health Summary</h2><p>{html.escape(_text(health.get('confidence_effect') or 'Evidence remains review-gated.'))}</p><p><b>Completed scanners:</b> {html.escape(_text(', '.join(health.get('completed_scanners') or []) or 'None retained'))}</p>{_html_table(['Scanner','Status','Required','Affected categories','Confidence impact','Remediation'],incomplete_rows or [['—','No incomplete structured scanner record','—','—','—','Continue monitoring']])}</section>
<section><h2>Canonical Technical Scorecard</h2>{_html_table(['Control','Technical score','Band','Evidence assurance','Summary'],score_rows)}</section>
<section class='wide'><h2>Executive Risk Register</h2>{_html_table(['Priority','Risk ID','Risk','Business impact','Confidence','Recommended action','Effort','Cost of inaction','Residual risk','Evidence locations'],risk_rows or [['—','—','No structured finding retained','Human review remains required','—','Verify evidence completeness','—','Not quantified','Unknown','—']])}</section>
<h2>Detailed Findings Register</h2>{finding_cards}
<section><h2>Architecture and Data Flow</h2><div class='flow'><span>Repository</span><b>→</b><span>Immutable Snapshot</span><b>→</b><span>Evidence</span><b>→</b><span>Interpretation</span><b>→</b><span>Business Inference</span><b>→</b><span>Recommendation</span><b>→</b><span>Verification</span><b>→</b><span>Human Review</span></div></section>
<h2>Six-Month Execution Roadmap</h2>{roadmap_html}
<section><h2>Staffing and Sequencing</h2><ul>{''.join(f"<li>Sequence {html.escape(_text(item.get('sequence')))}: <b>{html.escape(_text(item.get('role')))}</b> — {html.escape(_text(item.get('focus')))}</li>" for item in staffing if isinstance(item,dict)) or '<li>Requires stakeholder approval.</li>'}</ul></section>
<section><h2>How to Use This Report</h2><ol>{''.join(f'<li>{html.escape(_text(item))}</li>' for item in assessment.get('how_to_use_report') or []) or '<li>Complete exact-package human review before delivery.</li>'}</ol></section>
<section><h2>Scope Boundary and Unassessed Risk</h2>{_html_table(['Area','Boundary'],[[item.get('area'),item.get('boundary')] for item in boundaries] or [['Unassessed domains','Must not be interpreted as healthy']])}</section>
<section><h2>Assumption Register</h2>{_html_table(['ID','Category','Assumption','Source','Confidence','Sensitivity','Consequence if wrong'],[[item.get('assumption_id'),item.get('category'),item.get('description'),item.get('source'),item.get('confidence'),item.get('sensitivity'),item.get('consequence_if_wrong')] for item in assumptions] or [['—','—','No structured assumption retained','—','—','—','Human validation required']])}</section>
<h2>Evidence Appendix</h2>{stage_html}
<section><h2>Human Review and Acceptance Gate</h2><ul><li>Verify exact identities and immutable evidence.</li><li>Triage every material, review-required, failed, timed-out, and unavailable analyzer result.</li><li>Confirm cross-format technical score, Evidence-Adjusted score, assurance, and delivery truth.</li><li>Disposition every P1 against acceptance criteria and residual risk.</li><li>Approve or reject the exact immutable package.</li></ul><p class='warning'>{html.escape(_text(assessment.get('delivery_status') or 'HUMAN REVIEW REQUIRED'))} — CLIENT DELIVERY NOT AUTHORIZED WITHOUT EXACT-PACKAGE APPROVAL</p></section>
</main></body></html>"""


def _findings_csv(findings: list[dict[str, Any]]) -> str:
    # Preserve the historical prefix for downstream consumers while adding decision-grade columns.
    fields = ["id", "priority", "category", "title", "location", "finding_id", "fact", "interpretation", "evidence", "business_impact", "impact", "confidence", "owner_role", "effort", "recommendation", "acceptance_criteria", "cost_of_inaction", "residual_risk", "roadmap_mappings", "backlog_issue_mapping"]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in findings:
        if isinstance(item, dict):
            writer.writerow({field: _text(item.get(field), 6000) for field in fields})
    return stream.getvalue()


def _evidence_csv(stages: list[dict[str, Any]]) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["stage_id", "stage_title", "stage_status", "record_type", "record"])
    for stage in stages:
        for record_type in ("evidence", "findings", "unavailable"):
            for item in stage.get(record_type) or []:
                writer.writerow([stage.get("stage_id"), stage.get("title"), stage.get("status"), record_type, _text(item, 4000)])
    return stream.getvalue()


__all__ = ["_build_html", "_findings_csv", "_evidence_csv"]
