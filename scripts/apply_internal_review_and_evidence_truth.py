#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def append_once(path: Path, marker: str, content: str) -> None:
    source = path.read_text(encoding="utf-8")
    if marker in source:
        return
    path.write_text(source.rstrip() + "\n\n" + content.strip() + "\n", encoding="utf-8")


def patch_canonical_truth() -> None:
    path = ROOT / "nico/comprehensive_canonical_report_truth_v1.py"
    source = path.read_text(encoding="utf-8")
    if "def _evidence_completion_contract(" not in source:
        needle = '''def _review_limited_count(assessment: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    sections = {
        _text(item.get("id")): item
        for item in assessment.get("sections") or []
        if isinstance(item, dict)
    }
    count = 0
    for row in rows:
        if not row.get("included"):
            continue
        section = sections.get(_text(row.get("section_id")), {})
        assurance = _text(row.get("assurance") or section.get("assurance_label")).upper()
        if assurance and assurance not in {"VERIFIED", "COMPLETE"}:
            count += 1
    return count
'''
        addition = needle + '''

def _percent(completed: int, total: int) -> int | None:
    if total <= 0:
        return None
    return max(0, min(100, round((completed / total) * 100)))


def _evidence_completion_contract(
    assessment: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    sections = {
        _text(item.get("id")): item
        for item in assessment.get("sections") or []
        if isinstance(item, dict)
    }
    controls = [
        row for row in rows
        if isinstance(row, dict) and float(row.get("weight") or 0) > 0
    ]
    processed = 0
    disposed = 0
    for row in controls:
        section = sections.get(_text(row.get("section_id")), {})
        score = row.get("technical_score")
        assurance = _text(row.get("assurance") or section.get("assurance_label"))
        unavailable = [item for item in section.get("unavailable") or [] if _text(item)]
        findings = [item for item in section.get("findings") or [] if _text(item)]
        has_machine_result = isinstance(score, (int, float)) or bool(assurance)
        has_explicit_disposition = has_machine_result or bool(unavailable) or bool(findings)
        processed += int(has_machine_result)
        disposed += int(has_explicit_disposition)

    health = assessment.get("evidence_health_summary") if isinstance(assessment.get("evidence_health_summary"), dict) else {}
    completed_scanners = [item for item in health.get("completed_scanners") or [] if _text(item)]
    incomplete_scanners = [item for item in health.get("incomplete_scanners") or [] if isinstance(item, dict) or _text(item)]
    scanner_total = len(completed_scanners) + len(incomplete_scanners)

    legacy = assessment.get("evidence_coverage") if isinstance(assessment.get("evidence_coverage"), dict) else {}
    raw_overall = legacy.get("overall_percent", legacy.get("percent"))
    overall = int(round(float(raw_overall))) if isinstance(raw_overall, (int, float)) else None
    if overall is not None:
        overall = max(0, min(100, overall))

    automatable_percent = _percent(processed, len(controls))
    disposition_percent = _percent(disposed, len(controls))
    analyzer_percent = _percent(len(completed_scanners), scanner_total)
    gap = None if overall is None else max(0, 100 - overall)

    contract = {
        "version": VERSION,
        "automatable_repository_evidence": {
            "label": "Automatable repository evidence processed",
            "completed": processed,
            "total": len(controls),
            "percent": automatable_percent,
            "definition": "Standard repository evidence controls with a normalized machine result. This does not mean every analyzer succeeded.",
        },
        "required_evidence_disposition": {
            "label": "Required evidence disposition",
            "completed": disposed,
            "total": len(controls),
            "percent": disposition_percent,
            "definition": "Required repository controls with collected evidence or an explicit limitation, failure, or not-applicable disposition.",
        },
        "analyzer_completion": {
            "label": "Successful analyzer completion",
            "completed": len(completed_scanners),
            "total": scanner_total,
            "percent": analyzer_percent,
            "definition": "Configured analyzers that completed successfully. Failed or partial analyzers remain visible and can block approval.",
        },
        "overall_engagement_evidence": {
            "label": "Overall engagement evidence",
            "percent": overall,
            "gap_percent": gap,
            "definition": "Repository, runtime, infrastructure, stakeholder, business, and client-provided evidence available for this engagement.",
        },
        "full_automation_claim_allowed": bool(automatable_percent == 100 and processed == len(controls) and len(controls) > 0),
        "full_required_disposition_claim_allowed": bool(disposition_percent == 100 and disposed == len(controls) and len(controls) > 0),
        "full_engagement_coverage_claim_allowed": overall == 100,
        "missing_evidence_never_treated_as_clean": True,
        "single_source_of_truth": True,
    }
    return contract


def _evidence_contract_valid(contract: Any) -> bool:
    if not isinstance(contract, dict):
        return False
    for key in ("automatable_repository_evidence", "required_evidence_disposition", "analyzer_completion"):
        metric = contract.get(key)
        if not isinstance(metric, dict):
            return False
        completed = metric.get("completed")
        total = metric.get("total")
        percent = metric.get("percent")
        if not isinstance(completed, int) or not isinstance(total, int) or completed < 0 or total < 0 or completed > total:
            return False
        expected = _percent(completed, total)
        if percent != expected:
            return False
        if percent == 100 and not (total > 0 and completed == total):
            return False
    overall = contract.get("overall_engagement_evidence")
    if not isinstance(overall, dict):
        return False
    percent = overall.get("percent")
    if percent is not None and (not isinstance(percent, int) or not 0 <= percent <= 100):
        return False
    if contract.get("full_engagement_coverage_claim_allowed") is True and percent != 100:
        return False
    return contract.get("missing_evidence_never_treated_as_clean") is True
'''
        if needle not in source:
            raise RuntimeError("canonical review-limited function not found")
        source = source.replace(needle, addition, 1)

    old = '''    output["scoring_weights"] = rows
    output["canonical_score_contract"] = {'''
    new = '''    output["scoring_weights"] = rows
    evidence_contract = _evidence_completion_contract(output, rows)
    output["evidence_completion_contract"] = evidence_contract
    legacy_coverage = output.get("evidence_coverage") if isinstance(output.get("evidence_coverage"), dict) else {}
    overall_metric = evidence_contract["overall_engagement_evidence"]
    output["evidence_coverage"] = {
        **legacy_coverage,
        "calculated": True,
        "label": "Overall engagement evidence",
        "percent": overall_metric.get("percent"),
        "overall_percent": overall_metric.get("percent"),
        "automatable_percent": evidence_contract["automatable_repository_evidence"].get("percent"),
        "required_disposition_percent": evidence_contract["required_evidence_disposition"].get("percent"),
        "analyzer_completion_percent": evidence_contract["analyzer_completion"].get("percent"),
        "contract_version": VERSION,
    }
    output["canonical_score_contract"] = {'''
    if old in source:
        source = source.replace(old, new, 1)

    source = source.replace(
        '"staffing sequence, and a full evidence appendix. Human review and exact-package approval remain mandatory."',
        '"staffing sequence, and a full evidence appendix. Internal technical review and exact-package authorization remain mandatory before client delivery."',
    )

    old = '''    invariant = _score_invariant(output)
    quality = package.get("report_quality_contract") if isinstance(package.get("report_quality_contract"), dict) else {}'''
    new = '''    invariant = _score_invariant(output)
    canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    evidence_contract = assessment.get("evidence_completion_contract")
    evidence_invariant_passed = _evidence_contract_valid(evidence_contract)
    quality = package.get("report_quality_contract") if isinstance(package.get("report_quality_contract"), dict) else {}'''
    if old in source:
        source = source.replace(old, new, 1)

    old = '''            "severity_calibration_separates_evidence_blockers": True,
        }
    )'''
    new = '''            "severity_calibration_separates_evidence_blockers": True,
            "evidence_completion_contract_valid": evidence_invariant_passed,
            "evidence_completion_contract": evidence_contract if isinstance(evidence_contract, dict) else {},
            "full_evidence_claims_require_exact_counts": True,
        }
    )'''
    if old in source:
        source = source.replace(old, new, 1)

    old = '''    if output.get("status") == "complete" and invariant["status"] != "passed":
        output["status"] = "blocked"
        output["reason"] = "canonical_report_score_invariant_failed"'''
    new = '''    if output.get("status") == "complete" and invariant["status"] != "passed":
        output["status"] = "blocked"
        output["reason"] = "canonical_report_score_invariant_failed"
    if output.get("status") == "complete" and not evidence_invariant_passed:
        output["status"] = "blocked"
        output["reason"] = "canonical_evidence_completion_invariant_failed"'''
    if old in source:
        source = source.replace(old, new, 1)

    path.write_text(source, encoding="utf-8")


def patch_assessment_model() -> None:
    path = ROOT / "apps/web/app/assessment/assessmentModel.ts"
    source = path.read_text(encoding="utf-8")
    if "export function evidenceCompletionFor" not in source:
        marker = '''export function reportFor(_service: Service, result: Result | null): Report | null {
  if (!result) return null;
  for (const id of ["final_comprehensive_report_generation", "risk_reduction_and_executive_briefing", "decision_report_generation"]) {
    const value = stage(result, id);
    const report = value?.report_package || value?.reports;
    if (report) return report;
  }
  return result.reports || null;
}
'''
        addition = marker + '''

type CompletionMetric = {
  label: string;
  completed: number | null;
  total: number | null;
  percent: number | null;
  definition: string;
};

export type EvidenceCompletionView = {
  automatable: CompletionMetric;
  disposition: CompletionMetric;
  analyzers: CompletionMetric;
  overall: CompletionMetric & {gapPercent: number | null};
};

function completionMetric(value: unknown, fallbackLabel: string): CompletionMetric {
  const record = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const percent = typeof record.percent === "number" && Number.isFinite(record.percent)
    ? Math.max(0, Math.min(100, Math.round(record.percent)))
    : null;
  return {
    label: String(record.label || fallbackLabel),
    completed: typeof record.completed === "number" ? record.completed : null,
    total: typeof record.total === "number" ? record.total : null,
    percent,
    definition: String(record.definition || ""),
  };
}

export function evidenceCompletionFor(assessment: Assessment | null): EvidenceCompletionView | null {
  if (!assessment) return null;
  const contract = assessment.evidence_completion_contract;
  if (!contract || typeof contract !== "object" || Array.isArray(contract)) return null;
  const record = contract as Record<string, unknown>;
  const overall = completionMetric(record.overall_engagement_evidence, "Overall engagement evidence");
  const overallRecord = record.overall_engagement_evidence && typeof record.overall_engagement_evidence === "object"
    ? record.overall_engagement_evidence as Record<string, unknown>
    : {};
  return {
    automatable: completionMetric(record.automatable_repository_evidence, "Automatable repository evidence processed"),
    disposition: completionMetric(record.required_evidence_disposition, "Required evidence disposition"),
    analyzers: completionMetric(record.analyzer_completion, "Successful analyzer completion"),
    overall: {
      ...overall,
      gapPercent: typeof overallRecord.gap_percent === "number" ? overallRecord.gap_percent : null,
    },
  };
}

export type InternalReviewState = {
  approved: boolean;
  completed: boolean;
  deliveryAllowed: boolean;
  status: string;
};

export function internalReviewStateFor(result: Result | null): InternalReviewState {
  const record = result?.record && typeof result.record === "object" ? result.record as Record<string, unknown> : {};
  const status = String(result?.status || record.status || "").toLowerCase();
  const deliveryAllowed = result?.client_delivery_allowed === true || record.client_delivery_allowed === true;
  const completed = result?.human_review_completed === true || record.human_review_completed === true || status === "approved" || status === "rejected";
  return {
    approved: status === "approved" && deliveryAllowed,
    completed,
    deliveryAllowed,
    status,
  };
}

export function internalReviewHrefFor(result: Result | null, locale: string): string {
  const record = result?.record && typeof result.record === "object" ? result.record as Record<string, unknown> : {};
  const identity = record.identity && typeof record.identity === "object" && !Array.isArray(record.identity)
    ? record.identity as Record<string, unknown>
    : {};
  const params = new URLSearchParams({
    service: "comprehensive",
    run_id: String(result?.run_id || identity.run_id || ""),
    customer_id: String(result?.customer_id || identity.customer_id || "default_customer"),
    project_id: String(result?.project_id || identity.project_id || "default_project"),
    lang: locale === "es-MX" ? "es-MX" : "en",
  });
  return `/operations/final-review?${params.toString()}`;
}
'''
        if marker not in source:
            raise RuntimeError("assessment reportFor marker not found")
        source = source.replace(marker, addition, 1)

    old = '''export function terminal(_service: Service, result: Result): Phase | null {
  const value = String(result.status || result.record?.status || "").toLowerCase();
  if (["failed", "blocked", "error", "rejected", "interrupted"].includes(value)) return "failed";
  if (value === "review_required" || (["complete", "completed"].includes(value) && result.human_review_required !== false)) return "review_required";
  return null;
}'''
    new = '''export function terminal(_service: Service, result: Result): Phase | null {
  const value = String(result.status || result.record?.status || "").toLowerCase();
  const deliveryAllowed = result.client_delivery_allowed === true || result.record?.client_delivery_allowed === true;
  if (value === "approved" && deliveryAllowed) return "complete";
  if (["failed", "blocked", "error", "rejected", "interrupted"].includes(value)) return "failed";
  if (value === "review_required" || (["complete", "completed"].includes(value) && result.human_review_required !== false)) return "review_required";
  return null;
}'''
    if old in source:
        source = source.replace(old, new, 1)
    path.write_text(source, encoding="utf-8")


def patch_workspace() -> None:
    path = ROOT / "apps/web/app/assessment/AssessmentWorkspace.tsx"
    source = path.read_text(encoding="utf-8")
    if "evidenceCompletionFor," not in source:
        source = source.replace(
            '''  apiUrl,
  assessmentFor,
  compactIdentifier,''',
            '''  apiUrl,
  assessmentFor,
  compactIdentifier,
  evidenceCompletionFor,
  internalReviewHrefFor,
  internalReviewStateFor,''',
            1,
        )

    old = '''  const coverage = assessment?.evidence_coverage;
  const coverageLabel = coverage?.calculated && Number.isFinite(Number(coverage.percent))
    ? `${coverage.label || copy.evidence}: ${Math.max(0, Math.min(100, Number(coverage.percent)))}%`
    : copy.coverage;'''
    new = '''  const coverage = assessment?.evidence_coverage;
  const evidenceCompletion = evidenceCompletionFor(assessment);
  const primaryCoverage = evidenceCompletion?.automatable.percent;
  const coverageLabel = primaryCoverage != null
    ? `${copy.automatableEvidence}: ${primaryCoverage}%`
    : coverage?.calculated && Number.isFinite(Number(coverage.percent))
      ? `${coverage.label || copy.evidence}: ${Math.max(0, Math.min(100, Number(coverage.percent)))}%`
      : copy.coverage;'''
    if old in source:
        source = source.replace(old, new, 1)

    old = '''  const reviewStatus = phase === "review_required" ? copy.phases.review_required : running ? copy.reviewAfterReport : copy.awaitingStage;'''
    new = '''  const internalReview = internalReviewStateFor(result);
  const reviewStatus = internalReview.approved
    ? copy.internalReviewApproved
    : phase === "review_required"
      ? copy.internalReviewRequired
      : running ? copy.reviewAfterReport : copy.awaitingStage;
  const clientReadyStatus = internalReview.approved ? copy.clientReadyYes : copy.clientReadyNo;
  const internalReviewHref = internalReviewHrefFor(result, locale);'''
    if old in source:
        source = source.replace(old, new, 1)

    old = '''  const reportActions = <div
    className={`report-actions ${workspaceStyles.reportActionBar}`}'''
    new = '''  const reviewAction = result?.run_id && (phase === "review_required" || internalReview.completed)
    ? <a
      className={workspaceStyles.internalReviewAction}
      data-assessment-internal-review="true"
      href={internalReviewHref}
    >{internalReview.approved ? copy.openReviewRecord : copy.openInternalReview}</a>
    : null;

  const reportActions = <div
    className={`report-actions ${workspaceStyles.reportActionBar}`}'''
    if old in source:
        source = source.replace(old, new, 1)

    old = '''    <button type="button" disabled={!pdfAvailable || artifactAction !== null} onClick={downloadPdf}>{copy.download}</button>'''
    new = '''    <button type="button" disabled={!pdfAvailable || artifactAction !== null} onClick={downloadPdf}>{internalReview.approved ? copy.downloadApprovedPdf : copy.downloadReviewPdf}</button>'''
    if old in source:
        source = source.replace(old, new, 1)

    old = '''      </div>
      {!compactMobile ? <>
        <p className={workspaceStyles.sectionSummary}>{serviceCopy.summary}</p>'''
    new = '''      </div>
      {evidenceCompletion ? <div className={workspaceStyles.evidenceMetricGrid} data-assessment-evidence-metrics="true">
        {[evidenceCompletion.automatable, evidenceCompletion.disposition, evidenceCompletion.analyzers, evidenceCompletion.overall].map((metric) => <article key={metric.label} title={metric.definition}>
          <b>{metric.label}</b>
          <span>{metric.percent == null ? copy.notVerified : `${metric.percent}%`}</span>
          {metric.completed != null && metric.total != null ? <small>{metric.completed}/{metric.total}</small> : null}
        </article>)}
      </div> : null}
      {!compactMobile ? <>
        <p className={workspaceStyles.sectionSummary}>{serviceCopy.summary}</p>'''
    if old in source:
        source = source.replace(old, new, 1)

    old = '''            <article><b>{copy.review}</b><span>{reviewStatus}</span></article>
            <article><b>{copy.technicalMaturityLabel || copy.maturity}</b>'''
    new = '''            <article><b>{copy.review}</b><span>{reviewStatus}</span></article>
            <article><b>{copy.clientReady}</b><span>{clientReadyStatus}</span></article>
            <article><b>{copy.technicalMaturityLabel || copy.maturity}</b>'''
    if old in source:
        source = source.replace(old, new, 1)

    old = '''          {reportActions}
          {terminalView ? <div className={workspaceStyles.terminalActions}'''
    new = '''          {reportActions}
          {reviewAction}
          {terminalView ? <div className={workspaceStyles.terminalActions}'''
    source = source.replace(old, new, 1)

    old = '''          <div className="grid four target-grid"><article><b>{copy.review}</b><span>{reviewStatus}</span></article><article><b>{copy.technicalMaturityLabel || copy.maturity}</b>'''
    new = '''          <div className="grid four target-grid"><article><b>{copy.review}</b><span>{reviewStatus}</span></article><article><b>{copy.clientReady}</b><span>{clientReadyStatus}</span></article><article><b>{copy.technicalMaturityLabel || copy.maturity}</b>'''
    if old in source:
        source = source.replace(old, new, 1)

    old = '''          {reportActions}
          {terminalView ? <div className={workspaceStyles.terminalActions}'''
    new = '''          {reportActions}
          {reviewAction}
          {terminalView ? <div className={workspaceStyles.terminalActions}'''
    source = source.replace(old, new, 1)

    path.write_text(source, encoding="utf-8")


def patch_copy() -> None:
    path = ROOT / "apps/web/app/assessment/assessmentCopy.ts"
    source = path.read_text(encoding="utf-8")
    replacements = {
        'human_review_request: "Expert review request"': 'human_review_request: "Internal technical review"',
        'client_acceptance_pending: "Client acceptance pending"': 'client_acceptance_pending: "Client-ready authorization pending"',
        'heroBoundary: "Every finding is reviewed before it becomes a client recommendation."': 'heroBoundary: "Every client-facing recommendation is internally reviewed before release."',
        'trustIndicators: ["Exact repository snapshot", "Expert technical review", "Evidence traceability", "Independent quality control", "Human approval"]': 'trustIndicators: ["Exact repository snapshot", "Internal technical review", "Evidence traceability", "Independent quality control", "Controlled client release"]',
        'warning: "Only submit repositories that NICO is authorized to assess. Analysis is defensive and read-only; client delivery remains subject to technical and quality review."': 'warning: "Only submit repositories that NICO is authorized to assess. Analysis is defensive and read-only; client release requires internal technical approval."',
        'review: "Expert review"': 'review: "Internal review"',
        'reviewNotice: "Automated analysis is complete. The NICO technical team must review and approve this exact evidence-bound edition before client delivery."': 'reviewNotice: "Automated analysis is complete. An authorized NICO reviewer must approve this exact evidence-bound edition before it becomes client-ready."',
        'comprehensiveReview: "Technical analysis and report preparation are complete. The engagement is awaiting required human review."': 'comprehensiveReview: "Technical analysis and report preparation are complete. The engagement is awaiting internal technical review."',
        'review_required: "Expert review required"': 'review_required: "Internal review required"',
        '"Requires expert review and approval before client delivery."': '"Requires internal technical approval before client release."',
        '"Analyst review", "Report preparation", "Quality review", "Client delivery"': '"Internal technical review", "Report preparation", "Quality approval", "Client-ready release"',
        'human_review_request: "Solicitud de revisión experta"': 'human_review_request: "Revisión técnica interna"',
        'client_acceptance_pending: "Aceptación del cliente pendiente"': 'client_acceptance_pending: "Autorización para entrega pendiente"',
        'heroBoundary: "Cada hallazgo se revisa antes de convertirse en una recomendación para el cliente."': 'heroBoundary: "Cada recomendación para el cliente recibe revisión interna antes de su entrega."',
        'review: "Revisión experta"': 'review: "Revisión interna"',
        'reviewNotice: "El análisis automatizado terminó. El equipo técnico de NICO debe revisar y aprobar esta edición exacta antes de entregarla al cliente."': 'reviewNotice: "El análisis automatizado terminó. Un revisor autorizado de NICO debe aprobar esta edición exacta antes de que esté lista para el cliente."',
        'comprehensiveReview: "El análisis técnico y el informe están completos. El encargo espera la revisión humana obligatoria."': 'comprehensiveReview: "El análisis técnico y el informe están completos. El encargo espera la revisión técnica interna."',
        'review_required: "Revisión experta requerida"': 'review_required: "Revisión interna requerida"',
    }
    for old, new in replacements.items():
        source = source.replace(old, new)

    en_marker = '''  reviewNotice: "Automated analysis is complete. An authorized NICO reviewer must approve this exact evidence-bound edition before it becomes client-ready.",'''
    if en_marker in source and "openInternalReview:" not in source:
        source = source.replace(en_marker, en_marker + '''
  internalReviewRequired: "Internal review required",
  internalReviewApproved: "Internal review approved",
  clientReady: "Client-ready",
  clientReadyYes: "Yes · Approved",
  clientReadyNo: "No · Internal approval required",
  openInternalReview: "Open internal review",
  openReviewRecord: "Open approval record",
  downloadReviewPdf: "Download review PDF",
  downloadApprovedPdf: "Download approved PDF",
  automatableEvidence: "Automatable evidence processed",
  requiredEvidenceDisposition: "Required evidence disposition",
  analyzerCompletion: "Analyzer completion",
  overallEngagementEvidence: "Overall engagement evidence",''', 1)

    es_marker = '''  reviewNotice: "El análisis automatizado terminó. Un revisor autorizado de NICO debe aprobar esta edición exacta antes de que esté lista para el cliente.",'''
    if es_marker in source and source.count("openInternalReview:") < 2:
        source = source.replace(es_marker, es_marker + '''
  internalReviewRequired: "Revisión interna requerida",
  internalReviewApproved: "Revisión interna aprobada",
  clientReady: "Lista para el cliente",
  clientReadyYes: "Sí · Aprobada",
  clientReadyNo: "No · Requiere aprobación interna",
  openInternalReview: "Abrir revisión interna",
  openReviewRecord: "Abrir registro de aprobación",
  downloadReviewPdf: "Descargar PDF para revisión",
  downloadApprovedPdf: "Descargar PDF aprobado",
  automatableEvidence: "Evidencia automatizable procesada",
  requiredEvidenceDisposition: "Disposición de evidencia requerida",
  analyzerCompletion: "Finalización de analizadores",
  overallEngagementEvidence: "Evidencia total del encargo",''', 1)
    path.write_text(source, encoding="utf-8")


def patch_css() -> None:
    path = ROOT / "apps/web/app/assessment/engagementWorkspace.module.css"
    append_once(path, ".evidenceMetricGrid {", '''
.evidenceMetricGrid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 0 0 18px;
}

.evidenceMetricGrid article {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 12px 13px;
  border: 1px solid rgba(56, 189, 248, 0.18);
  border-radius: 12px;
  background: rgba(8, 47, 73, 0.18);
}

.evidenceMetricGrid b {
  color: #cbd5e1;
  font-size: 11px;
  line-height: 1.35;
}

.evidenceMetricGrid span {
  color: #67e8f9;
  font-size: 19px;
  font-weight: 720;
}

.evidenceMetricGrid small {
  color: #7f8da3;
  font-size: 10px;
}

.internalReviewAction {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  padding: 11px 16px;
  border: 1px solid rgba(251, 191, 36, 0.62);
  border-radius: 12px;
  background: rgba(120, 53, 15, 0.3);
  color: #fde68a;
  font-size: 13px;
  font-weight: 720;
  text-align: center;
  text-decoration: none;
}

.internalReviewAction:hover {
  background: rgba(146, 64, 14, 0.42);
}

@media (max-width: 760px) {
  .evidenceMetricGrid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 440px) {
  .evidenceMetricGrid {
    grid-template-columns: 1fr;
  }
}
''')


def patch_review_workspace() -> None:
    path = ROOT / "apps/web/app/operations/final-review/FinalReviewWorkspace.tsx"
    source = path.read_text(encoding="utf-8")
    replacements = {
        'eyebrow: "NICO CONTROLLED ACCEPTANCE"': 'eyebrow: "NICO INTERNAL QUALITY GATE"',
        'title: "Final review, without the friction."': 'title: "Internal final review and client-ready authorization."',
        'lead: "Review the exact immutable Strategic report, confirm its evidence boundary, and authorize only the artifact set you actually examined."': 'lead: "Review the exact immutable Comprehensive report, confirm its evidence boundary, and authorize only the artifact set your team actually examined."',
        'directRun: "Open this page from a completed assessment"': 'directRun: "Open this page from a completed Comprehensive assessment"',
        'delivery: "Client delivery"': 'delivery: "Client-ready"',
        'readyDelivery: "This exact immutable edition and its certified delivery package are approved for controlled client delivery."': 'readyDelivery: "This exact immutable edition and its certified delivery package are approved and client-ready."',
        'blockedDelivery: "Delivery remains blocked until a valid approval certificate matches the current artifact set."': 'blockedDelivery: "Client-ready release remains blocked until a valid internal approval certificate matches the current artifact set."',
        '`nico-strategic-delivery-${runId.trim()}-APPROVED.zip`': '`nico-comprehensive-delivery-${runId.trim()}-APPROVED.zip`',
        'eyebrow: "ACEPTACIÓN CONTROLADA DE NICO"': 'eyebrow: "CONTROL INTERNO DE CALIDAD NICO"',
        'title: "Revisión final, sin fricción."': 'title: "Revisión final interna y autorización para el cliente."',
        'lead: "Revisa el informe Estratégico inmutable exacto, confirma su límite de evidencia y autoriza únicamente el conjunto de artefactos que examinaste."': 'lead: "Revisa el informe Comprensivo inmutable exacto, confirma su límite de evidencia y autoriza únicamente el conjunto de artefactos que examinó tu equipo."',
        'delivery: "Entrega al cliente"': 'delivery: "Lista para el cliente"',
    }
    for old, new in replacements.items():
        source = source.replace(old, new)
    path.write_text(source, encoding="utf-8")


def patch_pdf_and_api_language() -> None:
    path = ROOT / "nico/comprehensive_express_quality_v7.py"
    source = path.read_text(encoding="utf-8")
    replacements = {
        '("REVIEW POSTURE", "Required", colors.HexColor("#fbbf24"))': '("INTERNAL REVIEW", "Required", colors.HexColor("#fbbf24"))',
        '("DELIVERY", "Draft only", colors.HexColor("#f472b6"))': '("CLIENT-READY", "No", colors.HexColor("#f472b6"))',
        '"READ-ONLY · IMMUTABLE SNAPSHOT · HUMAN REVIEW REQUIRED"': '"READ-ONLY · IMMUTABLE SNAPSHOT · INTERNAL REVIEW REQUIRED"',
        '"Not approved for client delivery"': '"Client-ready after internal approval"',
        '"The package adds deeper architecture, exact-location findings, roadmap, staffing, and evidence traceability to the Express baseline."': '"The assessment combines architecture, exact-location findings, roadmap, staffing, and evidence traceability in one Comprehensive package."',
        '"Complete exact-package human review"': '"Complete exact-package internal review"',
    }
    for old, new in replacements.items():
        source = source.replace(old, new)
    path.write_text(source, encoding="utf-8")

    path = ROOT / "nico/comprehensive_premium_pdf_v6.py"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "CLIENT DELIVERY NOT AUTHORIZED WITHOUT EXACT-PACKAGE APPROVAL",
        "CLIENT-READY RELEASE REQUIRES INTERNAL EXACT-PACKAGE APPROVAL",
    )
    source = source.replace(
        "an authorized human must approve the exact package.",
        "an authorized internal reviewer must approve the exact package before client release.",
    )
    source = source.replace(
        '"Exact-package approval required"',
        '"Internal exact-package approval required"',
    )
    path.write_text(source, encoding="utf-8")

    path = ROOT / "nico/comprehensive_api_routes.py"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        '"Operator admin authentication is required for Strategic review and approved delivery access."',
        '"Operator admin authentication is required for Comprehensive internal review and approved delivery access."',
    )
    source = source.replace("nico-strategic-delivery-", "nico-comprehensive-delivery-")
    path.write_text(source, encoding="utf-8")


def write_tests() -> None:
    path = ROOT / "tests/test_internal_review_and_evidence_truth_v1.py"
    path.write_text('''from __future__ import annotations

from pathlib import Path

from nico.comprehensive_canonical_report_truth_v1 import apply_canonical_score_truth

ROOT = Path(__file__).resolve().parents[1]


def _assessment(*, missing_control: bool = False) -> dict:
    scores = [
        ("code_audit", 0.20, 92, "VERIFIED"),
        ("dependency_health", 0.15, 92, "LIMITED · CANDIDATE DISPOSITION"),
        ("secrets_review", 0.15, 93, "LIMITED · CANDIDATE DISPOSITION"),
        ("static_analysis", 0.15, None if missing_control else 79, "" if missing_control else "LIMITED · ANALYZER COVERAGE"),
        ("ci_cd", 0.15, 86, "VERIFIED"),
        ("architecture_debt", 0.15, 78, "VERIFIED"),
        ("velocity_complexity", 0.05, 84, "VERIFIED"),
    ]
    return {
        "repository": "BoneManTGRM/NICO",
        "evidence_coverage": {"calculated": True, "percent": 81, "label": "Automated evidence coverage"},
        "evidence_health_summary": {
            "completed_scanners": ["scanner-a", "scanner-b", "scanner-c", "scanner-d"],
            "incomplete_scanners": [{"scanner": "bandit", "status": "failed"}, {"scanner": "eslint", "status": "failed"}],
        },
        "sections": [
            {
                "id": section_id,
                "score_value": score,
                "assurance_label": assurance,
                "unavailable": ["Required analyzer unavailable"] if missing_control and section_id == "static_analysis" else [],
            }
            for section_id, _weight, score, assurance in scores
        ],
        "scoring_weights": [
            {
                "section_id": section_id,
                "control": section_id,
                "weight": weight,
                "technical_score": score,
                "assurance": assurance,
                "included": score is not None,
            }
            for section_id, weight, score, assurance in scores
        ],
    }


def test_evidence_metrics_distinguish_processing_disposition_analyzers_and_overall() -> None:
    result = apply_canonical_score_truth(_assessment())
    contract = result["evidence_completion_contract"]

    assert contract["automatable_repository_evidence"]["percent"] == 100
    assert contract["automatable_repository_evidence"]["completed"] == 7
    assert contract["required_evidence_disposition"]["percent"] == 100
    assert contract["analyzer_completion"]["percent"] == 67
    assert contract["overall_engagement_evidence"]["percent"] == 81
    assert contract["overall_engagement_evidence"]["gap_percent"] == 19
    assert contract["full_automation_claim_allowed"] is True
    assert contract["full_engagement_coverage_claim_allowed"] is False
    assert result["evidence_coverage"]["automatable_percent"] == 100
    assert result["evidence_coverage"]["percent"] == 81


def test_missing_automatable_result_cannot_be_reported_as_100_percent() -> None:
    result = apply_canonical_score_truth(_assessment(missing_control=True))
    contract = result["evidence_completion_contract"]

    assert contract["automatable_repository_evidence"]["percent"] < 100
    assert contract["full_automation_claim_allowed"] is False
    assert contract["required_evidence_disposition"]["percent"] == 100


def test_completed_assessment_links_to_protected_internal_review() -> None:
    workspace = (ROOT / "apps/web/app/assessment/AssessmentWorkspace.tsx").read_text(encoding="utf-8")
    model = (ROOT / "apps/web/app/assessment/assessmentModel.ts").read_text(encoding="utf-8")

    assert 'data-assessment-internal-review="true"' in workspace
    assert "internalReviewHrefFor(result, locale)" in workspace
    assert "/operations/final-review?" in model
    assert 'service: "comprehensive"' in model
    assert 'run_id: String(result?.run_id' in model
    assert "X-NICO-Admin-Token" not in model


def test_approved_run_is_complete_and_client_ready_in_the_frontend_contract() -> None:
    model = (ROOT / "apps/web/app/assessment/assessmentModel.ts").read_text(encoding="utf-8")
    workspace = (ROOT / "apps/web/app/assessment/AssessmentWorkspace.tsx").read_text(encoding="utf-8")

    assert 'if (value === "approved" && deliveryAllowed) return "complete";' in model
    assert "clientReadyStatus" in workspace
    assert "internalReview.approved ? copy.downloadApprovedPdf : copy.downloadReviewPdf" in workspace


def test_visible_product_language_is_internal_review_not_client_acceptance() -> None:
    copy = (ROOT / "apps/web/app/assessment/assessmentCopy.ts").read_text(encoding="utf-8")
    review = (ROOT / "apps/web/app/operations/final-review/FinalReviewWorkspace.tsx").read_text(encoding="utf-8")
    pdf = (ROOT / "nico/comprehensive_express_quality_v7.py").read_text(encoding="utf-8")

    assert "Open internal review" in copy
    assert "Internal review approved" in copy
    assert "Internal final review and client-ready authorization" in review
    assert '"INTERNAL REVIEW"' in pdf
    assert '"CLIENT-READY"' in pdf
    assert '"Draft only"' not in pdf
''', encoding="utf-8")


def main() -> int:
    patch_canonical_truth()
    patch_assessment_model()
    patch_workspace()
    patch_copy()
    patch_css()
    patch_review_workspace()
    patch_pdf_and_api_language()
    write_tests()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
