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
        "<tr>" + "".join(f"<td>{html.escape(_text(value, 1200))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _build_html(identity: dict[str, Any], assessment: dict[str, Any], stages: list[dict[str, Any]], roadmap: list[dict[str, Any]], staffing: list[dict[str, Any]], limitations: dict[str, int], generated_at: str) -> str:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
    findings = [item for item in assessment.get("findings_register") or [] if isinstance(item, dict)]
    score_rows = [[item.get("label"), f"{item.get('score_value')}/100" if isinstance(item.get("score_value"), int) else "NOT SCORED", item.get("score_band_label"), item.get("assurance_label"), item.get("summary")] for item in sections]
    risk_rows = [[item.get("priority"), item.get("title"), item.get("impact"), item.get("confidence"), item.get("recommendation")] for item in findings[:12]]
    finding_cards = "".join(
        f"<section class='finding'><h3>{html.escape(_text(item.get('priority')))} · {html.escape(_text(item.get('title')))}</h3>"
        f"<dl><dt>Location</dt><dd>{html.escape(_text(item.get('location')))}</dd><dt>Evidence</dt><dd>{html.escape(_text(item.get('evidence')))}</dd>"
        f"<dt>Impact</dt><dd>{html.escape(_text(item.get('impact')))}</dd><dt>Owner / effort</dt><dd>{html.escape(_text(item.get('owner_role')))} · {html.escape(_text(item.get('effort')))}</dd>"
        f"<dt>Recommendation</dt><dd>{html.escape(_text(item.get('recommendation')))}</dd><dt>Acceptance</dt><dd>{html.escape(_text(item.get('acceptance_criteria')))}</dd></dl></section>"
        for item in findings
    ) or "<p>No structured technical finding was retained; human review remains required.</p>"
    roadmap_html = "".join(
        f"<section><h3>{html.escape(_text(window.get('window')))} — {html.escape(_text(window.get('objective')))}</h3>"
        + "".join(
            f"<article class='work'><h4>{html.escape(_text(package.get('title')))}</h4><p><b>Owner:</b> {html.escape(_text(package.get('owner_role')))} · <b>Effort:</b> {html.escape(_text(package.get('effort')))}</p>"
            f"<p>{html.escape(_text(package.get('objective')))}</p><p><b>Acceptance:</b> {html.escape('; '.join(package.get('acceptance_criteria') or []))}</p></article>"
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
    title = f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>
:root{{color-scheme:dark}}body{{margin:0;background:#071124;color:#dbeafe;font:16px/1.55 Inter,system-ui,sans-serif}}main{{max-width:1180px;margin:auto;padding:32px 20px 80px}}header,section,article{{border:1px solid #29405e;background:#0b172c;border-radius:18px;padding:22px;margin:16px 0}}h1{{font-size:clamp(28px,5vw,48px);margin:.2em 0}}h2{{color:#7dd3fc;border-top:1px solid #29405e;padding-top:26px;margin-top:38px}}h3{{color:#e0f2fe}}p,li,dd{{color:#cbd5e1}}.badge{{display:inline-block;padding:7px 11px;border-radius:999px;border:1px solid #f59e0b;background:#422006;color:#fde68a;font-weight:800}}table{{width:100%;border-collapse:collapse;margin:14px 0;font-size:14px}}th,td{{border:1px solid #334155;padding:9px;vertical-align:top}}th{{background:#0c4a6e;color:white;text-align:left}}tr:nth-child(even){{background:#0f1e35}}dl{{display:grid;grid-template-columns:minmax(120px,180px) 1fr;gap:7px 14px}}dt{{font-weight:800;color:#7dd3fc}}dd{{margin:0}}.flow{{display:flex;flex-wrap:wrap;gap:8px;align-items:center}}.flow span{{padding:12px;border:1px solid #38bdf8;border-radius:12px;background:#0c2a43}}.flow b{{color:#7dd3fc}}.warning{{border-color:#f59e0b;background:#422006;color:#fde68a;font-weight:800}}@media(max-width:760px){{table{{display:block;overflow-x:auto}}dl{{grid-template-columns:1fr}}}}
</style></head><body><main><header><h1>{html.escape(title)}</h1><p>Generated {html.escape(generated_at)}</p><span class='badge'>DRAFT · HUMAN REVIEW REQUIRED</span></header>
<section><h2>Executive Decision Brief</h2><p>{html.escape(_decision_summary(identity, assessment, limitations))}</p><p class='warning'>Client delivery is not authorized until an approved human review record exists.</p></section>
<section><h2>Assessment Dashboard</h2>{_html_table(['Dimension','Result','Meaning'], [['Technical maturity', f"{maturity.get('score_band_label') or _score_band(score)['score_band_label']} · {int(score)}/100" if isinstance(score,(int,float)) else 'NOT SCORED','Score-derived engineering health'],['Evidence readiness',maturity.get('evidence_readiness_score') or 'Pending','Completeness and reliability of required evidence'],['Human review','REQUIRED','Findings and assumptions remain human responsibilities'],['Client delivery','NOT AUTHORIZED','Approval required for the exact package']])}</section>
<section><h2>Limitation Accounting</h2>{_html_table(['Metric','Count','Definition'], [['Stages with limitations',limitations['stages_with_limitations'],'Stages with at least one limitation'],['Distinct limitation records',limitations['individual_limitation_records'],'Deduplicated records'],['Score-affecting records',limitations['score_affecting_records'],'Section findings or gaps'],['Informational records',limitations['informational_records'],'Non-score disclosures']])}</section>
<section><h2>Canonical Technical Scorecard</h2>{_html_table(['Control','Technical score','Band','Evidence assurance','Summary'],score_rows)}</section>
<section><h2>Executive Risk Register</h2>{_html_table(['Priority','Finding','Business impact','Confidence','Recommended action'],risk_rows or [['—','No structured finding retained','Human review remains required','—','Verify evidence completeness']])}</section>
<h2>Detailed Findings Register</h2>{finding_cards}
<section><h2>Architecture and Data Flow</h2><div class='flow'><span>Repository</span><b>→</b><span>Immutable Snapshot</span><b>→</b><span>Evidence Workers</span><b>→</b><span>Scoring & Reconciliation</span><b>→</b><span>Decision Report</span><b>→</b><span>Human Review</span></div></section>
<h2>Six-Month Execution Roadmap</h2>{roadmap_html}
<section><h2>Staffing and Sequencing</h2><ul>{''.join(f"<li>Sequence {html.escape(_text(item.get('sequence')))}: <b>{html.escape(_text(item.get('role')))}</b> — {html.escape(_text(item.get('focus')))}</li>" for item in staffing if isinstance(item,dict)) or '<li>Requires stakeholder approval.</li>'}</ul></section>
<h2>Evidence Appendix</h2>{stage_html}
<section><h2>Human Review and Acceptance Gate</h2><ul><li>Verify exact identities and immutable evidence.</li><li>Triage every material, review-required, failed, timed-out, and unavailable analyzer result.</li><li>Confirm cross-format score, assurance, and delivery truth.</li><li>Approve or reject the exact immutable package.</li></ul><p class='warning'>DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED</p></section>
</main></body></html>"""


def _findings_csv(findings: list[dict[str, Any]]) -> str:
    fields = ["id", "priority", "category", "title", "location", "evidence", "impact", "confidence", "owner_role", "effort", "recommendation", "acceptance_criteria"]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in findings:
        if isinstance(item, dict):
            writer.writerow({field: _text(item.get(field), 4000) for field in fields})
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
