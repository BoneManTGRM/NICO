"use client";

import {useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type MidDraftReport = {
  status?: string;
  draft_status?: string;
  report_version?: string;
  report_type?: string;
  report_path?: string;
  report_id?: string;
  run_id?: string;
  repository?: string;
  snapshot_id?: string;
  snapshot_commit_sha?: string;
  review_packet_id?: string;
  review_packet_sha256?: string;
  source_identity_sha256?: string;
  pdf_sha256?: string;
  pdf_filename?: string;
  generated_at?: string;
  evidence_coverage?: {percent?: number; numerator?: number; denominator?: number; method?: string};
  executive_summary?: Record<string, unknown>;
  human_review_required?: boolean;
  approval_required?: boolean;
  client_delivery_allowed?: boolean;
  approved?: boolean;
  unsupported_claims_permitted?: number;
  idempotent_reuse?: boolean;
  formats_available?: Record<string, boolean>;
  rule?: string;
};

function filenameFromDisposition(value: string | null): string {
  const match = String(value || "").match(/filename="?([^";]+)"?/i);
  return match?.[1] || "nico-mid-assessment-DRAFT.pdf";
}

function savePdf(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function statusClass(value?: string) {
  if (["complete", "human_review_required"].includes(String(value || "").toLowerCase())) return "status yellow";
  if (["blocked", "failed"].includes(String(value || "").toLowerCase())) return "status red";
  return "status gray";
}

export default function MidReportPage() {
  const [runId, setRunId] = useState("");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [adminToken, setAdminToken] = useState("");
  const [report, setReport] = useState<MidDraftReport | null>(null);
  const [generating, setGenerating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  async function readJson(response: Response) {
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail?.message || `Mid report request failed with ${response.status}.`);
    return data;
  }

  async function generateDraft() {
    if (!API_URL || !runId.trim() || !adminToken.trim() || generating) return;
    setError("");
    setReport(null);
    setGenerating(true);
    try {
      const response = await fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId.trim())}/report/draft`, {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-NICO-Admin-Token": adminToken},
        body: JSON.stringify({customer_id: customerId.trim() || "default_customer", project_id: projectId.trim() || "default_project"}),
        cache: "no-store",
      });
      const data = await readJson(response) as MidDraftReport;
      if (data.status !== "complete" || data.report_path !== "mid_run" || data.report_type !== "mid_assessment") {
        throw new Error("The backend did not return a valid Mid draft identity.");
      }
      if (data.approved || data.client_delivery_allowed || !data.human_review_required) {
        throw new Error("The returned artifact violated the Mid draft delivery boundary.");
      }
      setReport(data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Mid draft report generation failed.");
    } finally {
      setGenerating(false);
    }
  }

  async function downloadDraftPdf() {
    if (!API_URL || !runId.trim() || !adminToken.trim() || !report || downloading) return;
    setError("");
    setDownloading(true);
    try {
      const params = new URLSearchParams({customer_id: customerId.trim() || "default_customer", project_id: projectId.trim() || "default_project"});
      const response = await fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId.trim())}/report/draft/pdf?${params.toString()}`, {
        headers: {"X-NICO-Admin-Token": adminToken},
        cache: "no-store",
      });
      if (!response.ok) {
        let message = `Mid draft PDF download failed with ${response.status}.`;
        try {
          const data = await response.json() as {detail?: {message?: string}};
          message = data.detail?.message || message;
        } catch {
          // Keep the generic message.
        }
        throw new Error(message);
      }
      const reportId = response.headers.get("X-NICO-Report-ID") || "";
      const pdfSha = response.headers.get("X-NICO-PDF-SHA256") || "";
      const packetSha = response.headers.get("X-NICO-Review-Packet-SHA256") || "";
      const sourceSha = response.headers.get("X-NICO-Source-Identity-SHA256") || "";
      const reportPath = response.headers.get("X-NICO-Report-Path") || "";
      if (reportId !== report.report_id || pdfSha !== report.pdf_sha256 || packetSha !== report.review_packet_sha256 || sourceSha !== report.source_identity_sha256 || reportPath !== "mid_run") {
        throw new Error("The Mid draft PDF response did not match the generated report identity.");
      }
      const blob = await response.blob();
      if (!blob.size || blob.type !== "application/pdf") throw new Error("The Mid draft PDF response failed content validation.");
      savePdf(blob, filenameFromDisposition(response.headers.get("Content-Disposition")));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Mid draft PDF download failed.");
    } finally {
      setDownloading(false);
    }
  }

  return <main className="shell">
    <section className="hero">
      <p className="eyebrow">NICO Mid Assessment</p>
      <h1>Draft report generation</h1>
      <p className="lead">Generate the professional Mid draft only after the exact run, snapshot, truth model, and review-by-exception packet are available.</p>
    </section>

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Reviewer access</p><h2>Generate exact Mid draft</h2></div><span className={statusClass(report?.draft_status)}>{report?.draft_status || "not generated"}</span></div>
      <p className="warning-box">Draft generation does not approve the assessment, create a client link, or enable client delivery. The admin token remains in browser state only.</p>
      <div className="form-grid">
        <label>Mid run ID<input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="midrun_..." /></label>
        <label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label>
        <label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label>
        <label>NICO admin token<input type="password" autoComplete="off" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} /></label>
      </div>
      <div className="report-actions">
        <button type="button" className="primary-button" disabled={!API_URL || !runId.trim() || !adminToken.trim() || generating} onClick={generateDraft}>{generating ? "Generating bound draft..." : "Generate Mid draft report"}</button>
        <button type="button" disabled={!report || downloading} onClick={downloadDraftPdf}>{downloading ? "Verifying PDF..." : "Download verified draft PDF"}</button>
      </div>
      {error ? <p className="error-box">{error}</p> : null}
    </section>

    {report ? <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Draft identity</p><h2>{report.report_id}</h2></div><span className="status yellow">Human review required</span></div>
      <div className="grid four target-grid">
        <article><b>Report path</b><span>{report.report_path}</span></article>
        <article><b>Report type</b><span>{report.report_type}</span></article>
        <article><b>Coverage</b><span>{report.evidence_coverage?.percent ?? 0}%</span></article>
        <article><b>Client delivery</b><span>{String(Boolean(report.client_delivery_allowed))}</span></article>
      </div>
      <details className="help-details" open><summary>Integrity bindings</summary><pre className="json-block">{JSON.stringify({
        run_id: report.run_id,
        repository: report.repository,
        snapshot_id: report.snapshot_id,
        snapshot_commit_sha: report.snapshot_commit_sha,
        review_packet_id: report.review_packet_id,
        review_packet_sha256: report.review_packet_sha256,
        source_identity_sha256: report.source_identity_sha256,
        pdf_sha256: report.pdf_sha256,
        report_version: report.report_version,
        approved: report.approved,
        human_review_required: report.human_review_required,
        approval_required: report.approval_required,
        client_delivery_allowed: report.client_delivery_allowed,
        unsupported_claims_permitted: report.unsupported_claims_permitted,
        idempotent_reuse: report.idempotent_reuse,
      }, null, 2)}</pre></details>
      <p className="muted">{report.rule}</p>
    </section> : null}
  </main>;
}
