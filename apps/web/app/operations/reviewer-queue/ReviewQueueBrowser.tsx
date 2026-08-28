"use client";

import {useEffect, useMemo, useState} from "react";
import styles from "./review-browser.module.css";

type JsonRecord = Record<string, unknown>;
type Locale = "en" | "es-MX";
type Projection = {
  candidates?: JsonRecord[];
  clusters?: JsonRecord[];
  queue_counts?: JsonRecord;
  workload_metrics?: JsonRecord;
  quality_control_sampling?: JsonRecord;
  ready_for_final_approval?: boolean;
};

type Queue = "all" | "critical_material" | "human_technical_review" | "new_automated_triage_complete" | "stable_carry_forward" | "quality_control_sample" | "human_disposition_completed";
type Sort = "risk" | "confidence_desc" | "confidence_asc" | "candidate_id";

const QUEUES: {value: Queue; en: string; es: string}[] = [
  {value: "all", en: "All canonical candidates", es: "Todos los candidatos canónicos"},
  {value: "critical_material", en: "Critical / material", es: "Críticos / materiales"},
  {value: "human_technical_review", en: "Human technical review", es: "Revisión técnica humana"},
  {value: "new_automated_triage_complete", en: "New automated triage complete", es: "Nuevo triaje automatizado completo"},
  {value: "stable_carry_forward", en: "Stable carry-forward", es: "Continuidad estable"},
  {value: "quality_control_sample", en: "Quality-control sample", es: "Muestra de control de calidad"},
  {value: "human_disposition_completed", en: "Human disposition completed", es: "Disposición humana completada"},
];

const SEVERITY_RANK: Record<string, number> = {critical: 5, material: 5, high: 4, medium: 3, moderate: 3, low: 2, informational: 1, info: 1};

function text(value: unknown): string {
  return String(value ?? "").trim();
}

function tr(locale: Locale, english: string, spanish: string): string {
  return locale === "es-MX" ? spanish : english;
}

function numberValue(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function boolValue(value: unknown): boolean {
  return value === true;
}

function responseError(payload: JsonRecord, status: number, locale: Locale): string {
  if (locale === "es-MX") {
    const detail = payload.detail;
    const detailRecord = detail && typeof detail === "object" ? detail as JsonRecord : {};
    const rawCode = text(detailRecord.code);
    const code = /^[A-Z0-9_.-]+$/.test(rawCode) ? rawCode : "";
    return `No fue posible completar la solicitud protegida de revisión (HTTP ${status}${code ? ` · ${code}` : ""}).`;
  }
  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return text(payload.error) || `HTTP ${status}`;
}

function searchHaystack(candidate: JsonRecord): string {
  const keys = [
    "candidate_id", "finding_id", "path", "file_path", "package", "package_name",
    "advisory", "advisory_id", "rule", "rule_id", "scanner", "category", "manifest",
    "cluster_id", "technical_triage_verdict", "severity",
  ];
  return keys.map((key) => text(candidate[key])).join(" ").toLocaleLowerCase();
}

function unique(candidates: JsonRecord[], key: string): string[] {
  return [...new Set(candidates.map((candidate) => text(candidate[key])).filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function renderDetail(candidate: JsonRecord): string {
  return JSON.stringify(candidate, null, 2);
}

export default function ReviewQueueBrowser() {
  const [locale, setLocale] = useState<Locale>("en");
  const [runId, setRunId] = useState("");
  const [adminToken, setAdminToken] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [reviewerRole, setReviewerRole] = useState("");
  const [projection, setProjection] = useState<Projection | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [queue, setQueue] = useState<Queue>("all");
  const [severity, setSeverity] = useState("all");
  const [verdict, setVerdict] = useState("all");
  const [confidence, setConfidence] = useState("all");
  const [lineage, setLineage] = useState("all");
  const [scanner, setScanner] = useState("all");
  const [category, setCategory] = useState("all");
  const [disposition, setDisposition] = useState("all");
  const [attention, setAttention] = useState("all");
  const [sort, setSort] = useState<Sort>("risk");
  const [query, setQuery] = useState("");
  const [samplingStrategy, setSamplingStrategy] = useState("deterministic");
  const [sampleSize, setSampleSize] = useState("");

  useEffect(() => {
    const params = new URL(window.location.href).searchParams;
    const requestedLocale: Locale = params.get("lang") === "es-MX" ? "es-MX" : "en";
    setRunId(params.get("run_id") || "");
    setLocale(requestedLocale);
    document.documentElement.lang = requestedLocale;
    document.title = tr(requestedLocale, "Human review workspace | NICO", "Espacio de revisión humana | NICO");
  }, []);

  const endpoint = useMemo(
    () => `/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/review-work`,
    [runId],
  );

  async function load(): Promise<void> {
    if (!runId.trim() || !adminToken.trim()) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(endpoint, {
        method: "GET",
        cache: "no-store",
        headers: {Accept: "application/json", "X-NICO-Admin-Token": adminToken},
      });
      const payload = await response.json().catch(() => ({})) as Projection & JsonRecord;
      if (!response.ok) throw new Error(responseError(payload, response.status, locale));
      setProjection(payload);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(locale === "es-MX" ? (message.startsWith("No fue posible") ? message : "No fue posible cargar la verdad protegida de revisión.") : message);
    } finally {
      setBusy(false);
    }
  }

  async function configureSampling(): Promise<void> {
    if (!runId.trim() || !adminToken.trim() || !reviewer.trim() || !reviewerRole.trim()) return;
    setBusy(true);
    setError("");
    try {
      const payload: JsonRecord = {
        action: "configure_qc_sampling",
        reviewer: reviewer.trim(),
        reviewer_role: reviewerRole.trim(),
        review_authorized: true,
        authorization_confirmed: true,
        sampling_strategy: samplingStrategy,
      };
      if (sampleSize.trim()) payload.sample_size = Number.parseInt(sampleSize, 10);
      const response = await fetch(endpoint, {
        method: "POST",
        cache: "no-store",
        headers: {"Content-Type": "application/json", Accept: "application/json", "X-NICO-Admin-Token": adminToken},
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({})) as Projection & JsonRecord;
      if (!response.ok) throw new Error(responseError(result, response.status, locale));
      setProjection(result);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(locale === "es-MX" ? (message.startsWith("No fue posible") ? message : "No fue posible configurar la muestra de control de calidad.") : message);
    } finally {
      setBusy(false);
    }
  }

  const candidates = useMemo(
    () => (projection?.candidates || []).filter((candidate): candidate is JsonRecord => Boolean(candidate && typeof candidate === "object")),
    [projection],
  );
  const severities = useMemo(() => unique(candidates, "severity"), [candidates]);
  const verdicts = useMemo(() => unique(candidates, "technical_triage_verdict"), [candidates]);
  const lineages = useMemo(() => unique(candidates, "evidence_change_state"), [candidates]);
  const scanners = useMemo(() => unique(candidates, "scanner"), [candidates]);
  const categories = useMemo(() => unique(candidates, "category"), [candidates]);

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    const rows = candidates.filter((candidate) => {
      if (queue === "quality_control_sample" && !boolValue(candidate.quality_control_sample)) return false;
      if (queue !== "all" && queue !== "quality_control_sample" && text(candidate.primary_review_queue) !== queue) return false;
      if (severity !== "all" && text(candidate.severity) !== severity) return false;
      if (verdict !== "all" && text(candidate.technical_triage_verdict) !== verdict) return false;
      const candidateConfidence = numberValue(candidate.technical_triage_confidence);
      if (confidence === "low" && candidateConfidence >= 0.85) return false;
      if (confidence === "high" && candidateConfidence < 0.85) return false;
      if (lineage !== "all" && text(candidate.evidence_change_state) !== lineage) return false;
      if (scanner !== "all" && text(candidate.scanner) !== scanner) return false;
      if (category !== "all" && text(candidate.category) !== category) return false;
      if (disposition !== "all" && text(candidate.human_disposition_state) !== disposition) return false;
      if (attention === "individual" && !boolValue(candidate.individual_attention_required)) return false;
      if (attention === "grouped" && !boolValue(candidate.grouped_review_eligible)) return false;
      if (normalizedQuery && !searchHaystack(candidate).includes(normalizedQuery)) return false;
      return true;
    });
    return rows.sort((left, right) => {
      if (sort === "candidate_id") return text(left.candidate_id).localeCompare(text(right.candidate_id));
      if (sort === "confidence_desc") return numberValue(right.technical_triage_confidence) - numberValue(left.technical_triage_confidence);
      if (sort === "confidence_asc") return numberValue(left.technical_triage_confidence) - numberValue(right.technical_triage_confidence);
      const risk = (SEVERITY_RANK[text(right.severity).toLowerCase()] || 0) - (SEVERITY_RANK[text(left.severity).toLowerCase()] || 0);
      return risk || numberValue(left.technical_triage_confidence) - numberValue(right.technical_triage_confidence) || text(left.candidate_id).localeCompare(text(right.candidate_id));
    });
  }, [attention, candidates, category, confidence, disposition, lineage, query, queue, scanner, severity, sort, verdict]);

  const clusters = (projection?.clusters || []).filter((cluster): cluster is JsonRecord => Boolean(cluster && typeof cluster === "object"));
  const sampling = projection?.quality_control_sampling || {};
  const workload = projection?.workload_metrics || {};
  const queueCounts = projection?.queue_counts || {};

  return <section className={styles.panel} data-review-browser="phase2">
    <header className={styles.header}>
      <div>
        <p className={styles.eyebrow}>{tr(locale, "NICO COMPREHENSIVE · REVIEW BY EXCEPTION", "NICO COMPREHENSIVE · REVISIÓN POR EXCEPCIÓN")}</p>
        <h2>{tr(locale, "Canonical review queues, filtering, search, clusters, and QC sampling", "Colas canónicas de revisión, filtros, búsqueda, grupos y muestreo de control de calidad")}</h2>
        <p>{tr(locale, "NICO has already performed the repeatable technical analysis. Use these controls to isolate the evidence that needs professional attention. Full candidate evidence remains expandable.", "NICO ya realizó el análisis técnico reproducible. Usa estos controles para aislar la evidencia que requiere atención profesional. La evidencia completa de cada candidato permanece expandible.")}</p>
      </div>
      <span className={projection?.ready_for_final_approval ? styles.ready : styles.blocked}>{projection?.ready_for_final_approval ? tr(locale, "Review ready for separate final approval", "Revisión lista para la aprobación final separada") : tr(locale, "Final approval blocked", "Aprobación final bloqueada")}</span>
    </header>

    <div className={styles.credentials}>
      <label>{tr(locale, "Exact run ID", "ID exacto de la ejecución")}<input value={runId} onChange={(event) => setRunId(event.target.value)} autoComplete="off" /></label>
      <label>{tr(locale, "Operator admin token", "Token de administrador")}<input type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} autoComplete="off" /></label>
      <label>{tr(locale, "Authorized reviewer", "Revisor autorizado")}<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} autoComplete="off" /></label>
      <label>{tr(locale, "Reviewer role", "Función del revisor")}<input value={reviewerRole} onChange={(event) => setReviewerRole(event.target.value)} autoComplete="off" /></label>
      <button type="button" onClick={load} disabled={busy || !runId.trim() || !adminToken.trim()}>{busy ? tr(locale, "Working…", "Procesando…") : projection ? tr(locale, "Refresh review truth", "Actualizar verdad de revisión") : tr(locale, "Load review truth", "Cargar verdad de revisión")}</button>
    </div>
    <p className={styles.security}>{tr(locale, "The admin token remains only in page-local state and is sent only to the protected exact-run review endpoint.", "El token administrativo permanece únicamente en el estado local de la página y se envía solo al endpoint protegido de revisión de la ejecución exacta.")}</p>
    {error ? <p className={styles.error}>{error}</p> : null}

    {projection ? <>
      <div className={styles.metrics}>
        <article><strong>{text(workload.individual_attention_count) || "0"}</strong><span>{tr(locale, "individual attention", "atención individual")}</span></article>
        <article><strong>{text(workload.grouped_review_eligible_count) || "0"}</strong><span>{tr(locale, "grouped-review eligible", "elegibles para revisión agrupada")}</span></article>
        <article><strong>{text(workload.quality_control_sample_size) || "0"}</strong><span>{tr(locale, "QC sample", "muestra de control de calidad")}</span></article>
        <article><strong>{text(workload.human_dispositions_pending) || "0"}</strong><span>{tr(locale, "human dispositions pending", "disposiciones humanas pendientes")}</span></article>
        <article><strong>{text(workload.human_dispositions_completed) || "0"}</strong><span>{tr(locale, "human dispositions completed", "disposiciones humanas completadas")}</span></article>
        <article><strong>{text(workload.clusters_remaining) || "0"}</strong><span>{tr(locale, "clusters remaining", "grupos restantes")}</span></article>
        <article><strong>{text(workload.measured_specialist_hours) || "0"} h</strong><span>{tr(locale, "measured specialist time", "tiempo medido del especialista")}</span></article>
      </div>

      <div className={styles.queueStrip}>
        {QUEUES.slice(1).map((item) => <button key={item.value} type="button" className={queue === item.value ? styles.activeQueue : ""} onClick={() => setQueue(item.value)}><span>{locale === "es-MX" ? item.es : item.en}</span><b>{text(queueCounts[item.value]) || "0"}</b></button>)}
      </div>

      <div className={styles.filters}>
        <label>{tr(locale, "Queue", "Cola")}<select value={queue} onChange={(event) => setQueue(event.target.value as Queue)}>{QUEUES.map((item) => <option key={item.value} value={item.value}>{locale === "es-MX" ? item.es : item.en}</option>)}</select></label>
        <label>{tr(locale, "Severity", "Severidad")}<select value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="all">{tr(locale, "All", "Todas")}</option>{severities.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>{tr(locale, "Technical verdict", "Veredicto técnico")}<select value={verdict} onChange={(event) => setVerdict(event.target.value)}><option value="all">{tr(locale, "All", "Todos")}</option>{verdicts.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>{tr(locale, "Confidence", "Confianza")}<select value={confidence} onChange={(event) => setConfidence(event.target.value)}><option value="all">{tr(locale, "All", "Todas")}</option><option value="low">{tr(locale, "Below 0.85", "Menor que 0.85")}</option><option value="high">{tr(locale, "0.85 and above", "0.85 o mayor")}</option></select></label>
        <label>{tr(locale, "Evidence change", "Cambio en la evidencia")}<select value={lineage} onChange={(event) => setLineage(event.target.value)}><option value="all">{tr(locale, "All", "Todos")}</option>{lineages.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>{tr(locale, "Scanner", "Analizador")}<select value={scanner} onChange={(event) => setScanner(event.target.value)}><option value="all">{tr(locale, "All", "Todos")}</option>{scanners.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>{tr(locale, "Category", "Categoría")}<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="all">{tr(locale, "All", "Todas")}</option>{categories.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>{tr(locale, "Human disposition", "Disposición humana")}<select value={disposition} onChange={(event) => setDisposition(event.target.value)}><option value="all">{tr(locale, "All", "Todas")}</option><option value="pending">{tr(locale, "Pending", "Pendiente")}</option><option value="completed">{tr(locale, "Completed", "Completada")}</option></select></label>
        <label>{tr(locale, "Review mode", "Modalidad de revisión")}<select value={attention} onChange={(event) => setAttention(event.target.value)}><option value="all">{tr(locale, "All", "Todas")}</option><option value="individual">{tr(locale, "Individual attention", "Atención individual")}</option><option value="grouped">{tr(locale, "Grouped review eligible", "Elegible para revisión agrupada")}</option></select></label>
        <label>{tr(locale, "Sort", "Ordenar")}<select value={sort} onChange={(event) => setSort(event.target.value as Sort)}><option value="risk">{tr(locale, "Risk priority", "Prioridad de riesgo")}</option><option value="confidence_desc">{tr(locale, "Confidence high to low", "Confianza de mayor a menor")}</option><option value="confidence_asc">{tr(locale, "Confidence low to high", "Confianza de menor a mayor")}</option><option value="candidate_id">{tr(locale, "Candidate ID", "ID de candidato")}</option></select></label>
        <label className={styles.search}>{tr(locale, "Search candidate / finding / path / package / advisory / rule / scanner", "Buscar candidato / hallazgo / ruta / paquete / aviso / regla / analizador")}<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={tr(locale, "Exact ID or evidence term", "ID exacto o término de evidencia")} /></label>
      </div>

      <section className={styles.sampling}>
        <div><h3>{tr(locale, "Quality-control sampling", "Muestreo de control de calidad")}</h3><p>{tr(locale, "Sampling validates automation quality. It never approves unsampled candidates and never creates a human disposition.", "El muestreo valida la calidad de la automatización. Nunca aprueba candidatos no incluidos en la muestra ni crea una disposición humana.")}</p></div>
        <label>{tr(locale, "Strategy", "Estrategia")}<select value={samplingStrategy} onChange={(event) => setSamplingStrategy(event.target.value)}><option value="deterministic">{tr(locale, "Deterministic", "Determinista")}</option><option value="risk_weighted">{tr(locale, "Risk-weighted", "Ponderada por riesgo")}</option></select></label>
        <label>{tr(locale, "Sample size", "Tamaño de la muestra")}<input type="number" min="0" value={sampleSize} onChange={(event) => setSampleSize(event.target.value)} placeholder={text(sampling.sample_size) || tr(locale, "auto", "automático")} /></label>
        <button type="button" onClick={configureSampling} disabled={busy || !reviewer.trim() || !reviewerRole.trim()}>{tr(locale, "Configure explicit QC sample", "Configurar muestra explícita de control de calidad")}</button>
        <code>{text(sampling.sampling_version)}</code>
      </section>

      <div className={styles.resultHeader}><h3>{filtered.length} {tr(locale, filtered.length === 1 ? "candidate" : "candidates", filtered.length === 1 ? "candidato" : "candidatos")}</h3><button type="button" onClick={() => {setQueue("all"); setSeverity("all"); setVerdict("all"); setConfidence("all"); setLineage("all"); setScanner("all"); setCategory("all"); setDisposition("all"); setAttention("all"); setQuery("");}}>{tr(locale, "Clear filters", "Limpiar filtros")}</button></div>
      <div className={styles.candidates}>
        {!filtered.length ? <p>{tr(locale, "No canonical candidates match the selected filters.", "Ningún candidato canónico coincide con los filtros seleccionados.")}</p> : null}
        {filtered.map((candidate) => <details key={text(candidate.candidate_id)} className={styles.candidate}>
          <summary>
            <span><b>{text(candidate.candidate_id)}</b><small>{text(candidate.scanner) || text(candidate.category) || tr(locale, "canonical candidate", "candidato canónico")}</small></span>
            <span className={styles.badges}><i>{text(candidate.severity) || tr(locale, "unknown", "desconocida")}</i><i>{text(candidate.technical_triage_verdict) || tr(locale, "triage pending", "triaje pendiente")}</i><i>{text(candidate.human_disposition_state)}</i>{boolValue(candidate.quality_control_sample) ? <i>QC</i> : null}</span>
          </summary>
          <div className={styles.detailGrid}>
            <p><b>{tr(locale, "Cluster", "Grupo")}</b>{text(candidate.cluster_id) || "—"}</p><p><b>{tr(locale, "Confidence", "Confianza")}</b>{numberValue(candidate.technical_triage_confidence).toFixed(3)}</p><p><b>{tr(locale, "Path", "Ruta")}</b>{text(candidate.path) || text(candidate.file_path) || "—"}</p><p><b>{tr(locale, "Package / advisory", "Paquete / aviso")}</b>{text(candidate.package) || text(candidate.package_name) || text(candidate.advisory) || "—"}</p><p><b>{tr(locale, "Rule", "Regla")}</b>{text(candidate.rule) || text(candidate.rule_id) || "—"}</p><p><b>{tr(locale, "Evidence change", "Cambio en la evidencia")}</b>{text(candidate.evidence_change_state) || "—"}</p><p><b>{tr(locale, "Primary queue", "Cola principal")}</b>{text(candidate.primary_review_queue)}</p><p><b>{tr(locale, "Review mode", "Modalidad de revisión")}</b>{boolValue(candidate.individual_attention_required) ? tr(locale, "Individual", "Individual") : boolValue(candidate.grouped_review_eligible) ? tr(locale, "Grouped eligible", "Elegible para agrupación") : tr(locale, "Standard", "Estándar")}</p>
          </div>
          <pre>{renderDetail(candidate)}</pre>
        </details>)}
      </div>

      <section className={styles.clusters}>
        <h3>{tr(locale, "Clusters", "Grupos")}</h3>
        <p>{tr(locale, "Clusters summarize homogeneous review work. Expand any cluster to inspect its exact underlying candidate IDs and retained metadata.", "Los grupos resumen trabajo homogéneo de revisión. Expande cualquier grupo para inspeccionar los ID exactos de sus candidatos subyacentes y los metadatos conservados.")}</p>
        {clusters.map((cluster) => {
          const count = Array.isArray(cluster.candidate_ids) ? cluster.candidate_ids.length : 0;
          return <details key={text(cluster.cluster_id)}><summary><b>{text(cluster.cluster_id)}</b><span>{count} {tr(locale, count === 1 ? "candidate" : "candidates", count === 1 ? "candidato" : "candidatos")}</span></summary><pre>{JSON.stringify(cluster, null, 2)}</pre></details>;
        })}
      </section>
    </> : null}
  </section>;
}
