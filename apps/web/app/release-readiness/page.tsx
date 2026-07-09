"use client";

import {useEffect, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type ReleaseReadinessDiagnostics = {
  status?: string;
  generated_at?: string;
  route?: string;
  purpose?: string;
  patch_chain?: Record<string, boolean>;
  required_summary_keys?: string[];
  required_report_export_keys?: string[];
  summary_schema?: string;
  client_delivery_allowed_default?: boolean;
  missing_components?: string[];
  blockers?: string[];
  guardrail?: string;
};

function statusClass(status?: string) {
  if (status === "ok" || status === "ready" || status === "passed") return "status green";
  if (status === "incomplete" || status === "warning" || status === "queued") return "status yellow";
  if (status === "failed" || status === "error" || status === "blocked") return "status red";
  return "status gray";
}

function ListBlock({items}: {items?: string[]}) {
  if (!items?.length) return <p className="muted">None returned.</p>;
  return <ul className="tight-list">{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}

export default function ReleaseReadinessPage() {
  const [data, setData] = useState<ReleaseReadinessDiagnostics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadDiagnostics() {
    if (!API_URL) {
      setError("Backend URL is not configured in Vercel.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/diagnostics/release-readiness`, {cache: "no-store"});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.error || `Release-readiness diagnostics failed with ${response.status}`);
      setData(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Release-readiness diagnostics failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDiagnostics();
  }, []);

  const patchEntries = Object.entries(data?.patch_chain || {});

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO hosted readiness diagnostics</p>
        <h1>Release Readiness Verification</h1>
        <p className="lead">This page confirms that release-readiness summary support is installed. It does not approve client delivery, lift scores, or replace human review.</p>
      </section>

      <section className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">Readiness route</p>
            <h2>{data?.status === "ok" ? "Readiness support installed" : data ? "Readiness support incomplete" : "Checking readiness support"}</h2>
          </div>
          <span className={statusClass(data?.status)}>{loading ? "loading" : data?.status || "not loaded"}</span>
        </div>
        {error ? <p className="error-box">{error}</p> : null}
        <p className="warning-box">Client delivery remains blocked by default. This page only verifies the installed readiness-support contract.</p>
        <div className="grid three inset-grid">
          <article><b>Summary schema</b><span>{data?.summary_schema || "not loaded"}</span></article>
          <article><b>Missing components</b><span>{data?.missing_components?.length ?? 0}</span></article>
          <article><b>Client delivery default</b><span>{String(data?.client_delivery_allowed_default ?? false)}</span></article>
        </div>
        <button type="button" className="primary-button" disabled={loading || !API_URL} onClick={loadDiagnostics}>{loading ? "Checking..." : "Refresh readiness diagnostics"}</button>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Patch chain</p><h2>Installed readiness components</h2></div><span className={data?.missing_components?.length ? "status yellow" : data ? "status green" : "status gray"}>{patchEntries.filter(([, installed]) => installed).length}/{patchEntries.length || 0}</span></div>
        <div className="results-grid">
          {patchEntries.map(([name, installed]) => (
            <article className="result-card" key={name}>
              <div className="result-head"><b>{name}</b><span className={installed ? "status green" : "status red"}>{installed ? "installed" : "missing"}</span></div>
            </article>
          ))}
        </div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Blockers</p><h2>Readiness support blockers</h2></div><span className={data?.blockers?.length ? "status yellow" : "status green"}>{data?.blockers?.length || 0}</span></div>
        <ListBlock items={data?.blockers} />
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Output contract</p><h2>Required readiness fields</h2></div><span className="status blue">read only</span></div>
        <div className="results-grid">
          <article className="result-card">
            <h3>Summary keys</h3>
            <ListBlock items={data?.required_summary_keys} />
          </article>
          <article className="result-card">
            <h3>Report export keys</h3>
            <ListBlock items={data?.required_report_export_keys} />
          </article>
        </div>
        <p className="muted">Generated at: {data?.generated_at || "not loaded"}</p>
        <p className="muted">Route: {data?.route || "/diagnostics/release-readiness"}</p>
        <p className="muted">{data?.guardrail || "No guardrail returned yet."}</p>
      </section>
    </main>
  );
}
