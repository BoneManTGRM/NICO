#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"
TEST = ROOT / "tests" / "test_professional_assessment_ui.py"


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one exact source match, found {count}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"{label}: start marker not found")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"{label}: end marker not found")
    end_index += len(end)
    return text[:start_index] + replacement + text[end_index:]


def main() -> None:
    text = WORKSPACE.read_text(encoding="utf-8")

    text = replace_exact(
        text,
        "  pending: string;\n  notScored: string;",
        """  pending: string;
  awaitingStage: string;
  awaitingScanner: string;
  reviewAfterReport: string;
  maturityAfterScoring: string;
  notScoredYet: string;
  reviewLimitedNotScored: string;
  unavailableStatus: string;
  evidenceLimitations: string;
  baselineNotEstablished: string;
  inputNotProvided: string;
  notApplicable: string;
  runtimeAcceptanceNotProvided: string;
  awaitingCommercialInputs: string;
  copyValue: string;
  valueCopied: string;
  notScored: string;""",
        "Copy status fields",
    )

    text = replace_exact(
        text,
        '  pending: "Pending",\n  notScored: "Not scored",',
        '''  pending: "Pending",
  awaitingStage: "Awaiting stage",
  awaitingScanner: "Awaiting scanner completion",
  reviewAfterReport: "Begins after automated report",
  maturityAfterScoring: "Calculated after scoring",
  notScoredYet: "Not scored yet",
  reviewLimitedNotScored: "Review limited · Not scored",
  unavailableStatus: "Unavailable",
  evidenceLimitations: "Evidence limitations",
  baselineNotEstablished: "Baseline not established",
  inputNotProvided: "Input not provided",
  notApplicable: "Not applicable",
  runtimeAcceptanceNotProvided: "Runtime acceptance not provided",
  awaitingCommercialInputs: "Awaiting commercial inputs",
  copyValue: "Copy full value",
  valueCopied: "Copied",
  notScored: "Not scored",''',
        "English status copy",
    )

    text = replace_exact(
        text,
        '  pending: "Pendiente",\n  notScored: "Sin puntuación",',
        '''  pending: "Pendiente",
  awaitingStage: "En espera de la etapa",
  awaitingScanner: "En espera de que finalicen los analizadores",
  reviewAfterReport: "Comienza después del informe automatizado",
  maturityAfterScoring: "Se calcula después de la puntuación",
  notScoredYet: "Aún sin puntuación",
  reviewLimitedNotScored: "Revisión limitada · Sin puntuación",
  unavailableStatus: "No disponible",
  evidenceLimitations: "Limitaciones de evidencia",
  baselineNotEstablished: "Línea base aún no establecida",
  inputNotProvided: "Información no proporcionada",
  notApplicable: "No aplica",
  runtimeAcceptanceNotProvided: "Aceptación en ejecución no proporcionada",
  awaitingCommercialInputs: "En espera de datos comerciales",
  copyValue: "Copiar valor completo",
  valueCopied: "Copiado",
  notScored: "Sin puntuación",''',
        "Spanish status copy",
    )

    helpers = '''function statusClass(status?: string): string {
  const value = String(status || "").toLowerCase();
  if (["green", "complete", "completed", "attached", "verified", "review_required"].includes(value)) return "status green";
  if (["yellow", "pending", "running", "queued", "planned", "ready", "starting", "skipped"].includes(value)) return "status yellow";
  if (["red", "failed", "blocked", "error", "unavailable", "timed_out", "interrupted", "rejected"].includes(value)) return "status red";
  return "status gray";
}

function compactIdentifier(value: string, lead = 12, tail = 8): string {
  const normalized = String(value || "").trim();
  if (normalized.length <= lead + tail + 1) return normalized;
  return `${normalized.slice(0, lead)}…${normalized.slice(-tail)}`;
}

function formatStatus(status: unknown, copy: Copy): string {
  const raw = String(status || "").trim();
  const value = raw.toLowerCase().replace(/[\\s-]+/g, "_");
  if (!value) return copy.notVerified;
  if (value.includes("review_limited") && value.includes("not_scored")) return copy.reviewLimitedNotScored;
  if (["complete", "completed", "attached", "verified", "green"].includes(value)) return copy.phases.complete;
  if (["review_required", "human_review_required"].includes(value)) return copy.phases.review_required;
  if (["running", "starting", "in_progress"].includes(value)) return copy.phases.running;
  if (["pending", "queued", "planned", "ready", "not_started"].includes(value)) return copy.awaitingStage;
  if (["failed", "blocked", "error", "rejected", "interrupted"].includes(value)) return copy.phases.failed;
  if (["timed_out", "timeout"].includes(value)) return copy.phases.timed_out;
  if (value === "unavailable") return copy.unavailableStatus;
  if (value === "not_applicable") return copy.notApplicable;
  return value.split("_").filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function IdentifierValue({value, fallback, copy}: {value?: string; fallback: string; copy: Copy}) {
  const [didCopy, setDidCopy] = useState(false);
  const fullValue = String(value || "").trim();

  async function copyFullValue(): Promise<void> {
    if (!fullValue) return;
    try {
      await navigator.clipboard.writeText(fullValue);
      setDidCopy(true);
      window.setTimeout(() => setDidCopy(false), 1800);
    } catch {
      setDidCopy(false);
    }
  }

  return <span className="nico-identifier-value">
    <code title={fullValue || fallback}>{fullValue ? compactIdentifier(fullValue) : fallback}</code>
    {fullValue ? <button type="button" onClick={copyFullValue} aria-label={`${copy.copyValue}: ${fullValue}`}>{didCopy ? copy.valueCopied : copy.copyValue}</button> : null}
  </span>;
}'''

    text = replace_between(
        text,
        "function statusClass(status?: string): string {",
        "\n}\n\nfunction api(path: string): string {",
        helpers + "\n\nfunction api(path: string): string {",
        "status formatter helpers",
    )

    text = replace_exact(
        text,
        '  const scoreLabel = typeof scoreValue === "number" && Number.isFinite(scoreValue) ? `${scoreValue}/100` : copy.notScored;',
        '  const scoreLabel = typeof scoreValue === "number" && Number.isFinite(scoreValue) ? `${scoreValue}/100` : running ? copy.notScoredYet : copy.notScored;',
        "pending score copy",
    )

    text = replace_between(
        text,
        '  const scannerStatus = service === "express"',
        '  const reportStatus = report?.markdown || report?.html || report?.pdf_base64 ? copy.phases.complete : copy.pending;',
        '''  const scannerRawStatus = service === "express"
    ? result?.scanner_evidence?.scanner_status || result?.scanner?.status || result?.scanner_evidence?.status || (running ? "running" : "pending")
    : stage(result, "dependency_security_static_analysis")?.status || stage(result, "deep_scanner_triage")?.status || (running ? "running" : "pending");
  const scannerStatus = formatStatus(scannerRawStatus, copy);
  const reportStatus = report?.markdown || report?.html || report?.pdf_base64
    ? copy.phases.complete
    : running ? copy.awaitingScanner : copy.awaitingStage;
  const reviewStatus = phase === "review_required"
    ? copy.phases.review_required
    : running ? copy.reviewAfterReport : copy.awaitingStage;
  const maturityStatus = assessment?.maturity_signal?.level || (running ? copy.maturityAfterScoring : copy.awaitingStage);''',
        "derived assessment statuses",
    )

    text = replace_exact(
        text,
        '<div className="section-head"><div><p className="eyebrow">{copy.state}</p><h2>{result?.run_id || copy.phases[phase]}</h2></div><span className={statusClass(phase)}>{copy.phases[phase]}</span></div>',
        '<div className="section-head"><div><p className="eyebrow">{copy.state}</p><h2 title={result?.run_id}>{result?.run_id ? compactIdentifier(result.run_id, 18, 8) : copy.phases[phase]}</h2></div><span className={statusClass(phase)}>{copy.phases[phase]}</span></div>',
        "compact run heading",
    )

    cards_start = '        <div className="grid four target-grid"><article><b>{copy.runId}</b><span>{result.run_id || copy.notVerified}</span></article>'
    cards_end = '<article><b>{copy.durable}</b><span>{result.persistence?.durable ? copy.yes : result.persistence?.recorded ? copy.recorded : copy.notVerified}</span></article></div>'
    cards = '''        <div className="grid four target-grid">
          <article><b>{copy.runId}</b><IdentifierValue value={result.run_id} fallback={copy.notVerified} copy={copy} /></article>
          <article><b>{copy.commit}</b><IdentifierValue value={immutableCommit === "—" ? "" : immutableCommit} fallback={copy.notVerified} copy={copy} /></article>
          <article><b>{copy.scanner}</b><span>{scannerStatus}</span></article>
          <article><b>{copy.report}</b><span>{reportStatus}</span></article>
        </div>
        <div className="grid four target-grid">
          <article><b>{copy.review}</b><span>{reviewStatus}</span></article>
          <article><b>{copy.maturity}</b><span>{maturityStatus}</span></article>
          <article><b>{copy.score}</b><span>{scoreLabel}</span></article>
          <article><b>{copy.durable}</b><span>{result.persistence?.durable ? copy.yes : result.persistence?.recorded ? copy.recorded : copy.notVerified}</span></article>
        </div>'''
    text = replace_between(text, cards_start, cards_end, cards, "identity and status cards")

    timeline_start = '        {progressItems.length ? <div className={styles.timeline}>'
    timeline_end = '</div> : null}\n'
    timeline = '''        {progressItems.length ? <div className={styles.timeline}>{progressItems.map((item, index) => <article className="result-card" key={`${item.step}-${index}`}><div className="result-head"><b>{copy.stageLabels[String(item.step || "")] || String(item.step || copy.stage).replaceAll("_", " ")}</b><span className={statusClass(item.status)}>{formatStatus(item.status, copy)}</span></div><p>{item.message || copy.notVerified}</p>{item.evidence ? <details className="help-details"><summary>{copy.stepEvidence}</summary><pre className="json-block">{JSON.stringify(item.evidence, null, 2)}</pre></details> : null}</article>)}</div> : null}
'''
    text = replace_between(text, timeline_start, timeline_end, timeline, "timeline status formatting")

    sections_start = '        {assessment?.sections?.length ? <div className="results-grid">'
    sections_end = '</div> : null}\n'
    sections = '''        {assessment?.sections?.length ? <div className="results-grid">{assessment.sections.map((section, index) => {
          const value = section.presented_score ?? section.score;
          const score = typeof value === "number" ? `${value}/100` : copy.notScored;
          const rawState = section.presented_status || section.status || "unknown";
          const displayState = formatStatus(rawState, copy);
          const badge = typeof value === "number" ? `${displayState} · ${score}` : displayState === copy.reviewLimitedNotScored ? displayState : `${displayState} · ${score}`;
          return <article className="result-card" key={section.id || index}><div className="result-head"><b>{section.label || String(section.id || "").replaceAll("_", " ")}</b><span className={statusClass(rawState)}>{badge}</span></div><p>{section.summary}</p><details className="help-details"><summary>{copy.evidence} ({section.evidence?.length || 0})</summary><List items={section.evidence} empty={copy.notVerified} /></details>{section.findings?.length ? <details className="help-details"><summary>{copy.findings} ({section.findings.length})</summary><List items={section.findings} empty={copy.notVerified} /></details> : null}{section.unavailable?.length ? <details className="help-details"><summary>{copy.evidenceLimitations} ({section.unavailable.length})</summary><List items={section.unavailable} empty={copy.notVerified} /></details> : null}</article>;
        })}</div> : null}
'''
    text = replace_between(text, sections_start, sections_end, sections, "section status formatting")

    text = replace_exact(
        text,
        '<summary>{copy.unavailable} ({assessment.unavailable_data_notes.length})</summary>',
        '<summary>{copy.evidenceLimitations} ({assessment.unavailable_data_notes.length})</summary>',
        "assessment limitation summary",
    )

    WORKSPACE.write_text(text, encoding="utf-8")

    TEST.write_text(
        '''from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"
POLISH = ROOT / "apps" / "web" / "styles" / "professional-polish.css"


def test_status_copy_is_centralized_and_human_readable() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    for phrase in (
        "Awaiting stage",
        "Awaiting scanner completion",
        "Begins after automated report",
        "Calculated after scoring",
        "Not scored yet",
        "Review limited · Not scored",
        "Baseline not established",
        "Input not provided",
        "Not applicable",
        "Runtime acceptance not provided",
        "Awaiting commercial inputs",
    ):
        assert phrase in source
    assert "function formatStatus" in source
    assert "{item.status || copy.notVerified}" not in source
    assert "{state} · {label}" not in source
    assert "REVIEW_LIMITED_NOT_SCORED" not in source


def test_long_identifiers_are_compact_but_copyable() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    assert "function compactIdentifier" in source
    assert "function IdentifierValue" in source
    assert "Copy full value" in source
    assert "navigator.clipboard.writeText(fullValue)" in source
    assert "title={result?.run_id}" in source
    assert "immutableCommit === \"—\"" in source


def test_pending_stages_explain_their_dependencies() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    assert "running ? copy.awaitingScanner : copy.awaitingStage" in source
    assert "running ? copy.reviewAfterReport : copy.awaitingStage" in source
    assert "running ? copy.maturityAfterScoring : copy.awaitingStage" in source
    assert "running ? copy.notScoredYet : copy.notScored" in source


def test_mobile_identifier_controls_stay_contained() -> None:
    css = POLISH.read_text(encoding="utf-8")
    for marker in (
        ".nico-identifier-value",
        "overflow-wrap: anywhere",
        "word-break: break-word",
        "@media (max-width: 430px)",
    ):
        assert marker in css
''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
