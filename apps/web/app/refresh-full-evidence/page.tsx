"use client";

import {useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type ToolRecord = {
  tool?: string;
  category?: string;
  status?: string;
  returncode?: number | null;
  findings_count?: number;
  current_run?: boolean;
  verified_for_this_report?: boolean;
  reason?: string;
};

type RefreshResult = {
  status?: string;
  repository?: string;
  maturity_signal?: {level?: string; score?: number};
  human_review_required?: boolean;
  hosted_full_evidence_runtime_validation?: {
    status?: string;
    requested?: boolean;
    missing_or_unavailable_tools?: string[];
    tool_records?: ToolRecord[];
  };
  report_quality_guards?: {
    hosted_full_evidence_runtime?: {
      status?: string;
      refresh_full_evidence_requested?: boolean;
      missing_required_tools?: string[];
      missing_or_unavailable_tools?: string[];
      tool_records?: ToolRecord[];
      bandit_triage_summary?: {
        total_findings?: number;
        blocker_count?: number;
        needs_review_count?: number;
        static_lift_allowed?: boolean;
      };
    };
  };
  bandit_triage_summary?: {
    total_findings?: number;
    blocker_count?: number;
    needs_review_count?: number;
    static_lift_allowed?: boolean;
  };
  reports?: {pdf_base64?: string; pdf_filename?: string};
};

function statusClass(status?: string) {
  if (status === "completed" || status === "complete" || status === "green" || status === "success") return "status green";
  if (status === "failed" || status === "error" || status === "blocked" || status === "timeout") return "status red";
  if (status === "queued" || status === "running" || status === "yellow" || status === "unavailable" || status === "missing") return "status yellow";
  return "status gray";
}

function downloadPdf(result: RefreshResult | null) {
  const encoded = result?.reports?.pdf_base64;
  if (!encoded) return;
  const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0));
  const blob = new Blob([bytes], {type: "application/pdf"});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = result?.reports?.pdf_filename || "nico-refresh-full-evidence.pdf";
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function RefreshFullEvidencePage() {
  const [repository, setRepository] = useState("BoneManTGRM/NICO");
  const [authorized, setAuthorized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RefreshResult | null>(null);

  async function runRefreshFullEvidence() {
    if (!API_URL) {
      setError("Backend URL is not configured in Vercel.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/assessment/github`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          repository,
          authorized,
          client_name: "",
          project_name: "",
          assessment_mode: "express",
          timeframe_days: 180,
          authorized_by: "frontend-refresh-full-evidence",
          refresh_full_evidence_requested: true,
          run_scanner_worker: true,
          scanner_worker_autorun: true,
          full_history_secret_scan: true,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Refresh Full Evidence failed with ${response.status}`);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh Full Evidence failed");
    } finally {
      setLoading(false);
    }
  }

  const guard = result?.report_quality_guards?.hosted_full_evidence_runtime;
  const validation = result?.hosted_full_evidence_runtime_validation;
  const records = validation?.tool_records || guard?.tool_records || [];
  const bandit = result?.bandit_triage_summary || guard?.bandit_triage_summary;
  const missing = validation?.missing_or_unavailable_tools || guard?.missing_or_unavailable_tools || guard?.missing_required_tools || [];

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Refresh Full Evidence</p>
        <h1>Run hosted scanner evidence collection</h1>
        <p className="lead">This mode explicitly requests hosted scanner-worker execution, full-history secret scanning, current-run tool records, and strict human-review gating.</p>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Authorized repository</p><h2>Refresh Full Evidence request</h2></div><span className="status yellow">Evidence-bound</span></div>
        <p className="warning-box">Only run this on repositories you own or are explicitly authorized to assess. Missing, failed, or unavailable tools remain visible and do not count as clean evidence.</p>
        <label className="wide-label">Repository owner/name or GitHub URL<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repo" /></label>
        <label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />I confirm I own this target or have explicit permission to assess it.</label>
        <button type="button" className="primary-button" disabled={!API_URL || !authorized || loading} onClick={runRefreshFullEvidence}>{loading ? "Running Refresh Full Evidence..." : "Run Refresh Full Evidence"}</button>
        {error ? <p className="error-box">{error}</p> : null}
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Runtime validation</p><h2>{validation?.status || guard?.status || "No refresh result yet"}</h2></div><span className={statusClass(validation?.status || guard?.status)}>{result?.status || "not run"}</span></div>
        {result?.maturity_signal ? <p className="summary-box">{result.maturity_signal.level} · {result.maturity_signal.score}/100 · Human review required: {String(result.human_review_required)}</p> : null}
        <div className="grid three inset-grid">
          <article><b>Requested</b><span>{String(validation?.requested ?? guard?.refresh_full_evidence_requested ?? false)}</span></article>
          <article><b>Missing / unavailable</b><span>{missing.length}</span></article>
          <article><b>Bandit blockers</b><span>{bandit?.blocker_count ?? "unknown"}</span></article>
        </div>
        <div className="results-grid">
          {records.map((record) => (
            <article className="result-card" key={record.tool}>
              <div className="result-head"><b>{record.tool}</b><span className={statusClass(record.status)}>{record.status}</span></div>
              <p><b>Category:</b> {record.category || "unknown"}</p>
              <p><b>Return code:</b> {record.returncode ?? "n/a"}</p>
              <p><b>Findings:</b> {record.findings_count ?? 0}</p>
              <p><b>Current run:</b> {String(record.current_run)}</p>
              <p><b>Verified for this report:</b> {String(record.verified_for_this_report)}</p>
              {record.reason ? <p><b>Reason:</b> {record.reason}</p> : null}
            </article>
          ))}
        </div>
        <div className="report-actions"><button type="button" disabled={!result?.reports?.pdf_base64} onClick={() => downloadPdf(result)}>Download refreshed PDF</button></div>
      </section>
    </main>
  );
}
