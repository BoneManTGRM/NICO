"use client";

import {useEffect, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type ToolRecord = {
  tool: string;
  binary: string;
  category: string;
  required_for: string;
  path: string;
  installed: boolean;
  status: string;
  returncode: number | null;
  version: string;
  reason: string;
};

type RuntimeDiagnostics = {
  status?: string;
  generated_at?: string;
  purpose?: string;
  runtime?: {
    python_version?: string;
    platform?: string;
    cwd?: string;
    path_entries?: string[];
  };
  config?: Record<string, boolean | string>;
  tools?: ToolRecord[];
  summary?: {
    scanner_tools_installed?: string[];
    scanner_tools_missing?: string[];
    installed_count?: number;
    missing_count?: number;
    required_scanner_tool_count?: number;
    runtime_ready?: boolean;
  };
  blockers?: string[];
  guardrail?: string;
};

function statusClass(status?: string, installed?: boolean) {
  if (installed && status === "installed") return "status green";
  if (status === "command_failed") return "status yellow";
  if (status === "not_installed" || status === "failed" || status === "timeout") return "status red";
  return installed ? "status green" : "status gray";
}

function ListBlock({items}: {items?: string[]}) {
  if (!items?.length) return <p className="muted">None returned.</p>;
  return <ul className="tight-list">{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}

export default function ScannerRuntimePage() {
  const [data, setData] = useState<RuntimeDiagnostics | null>(null);
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
      const response = await fetch(`${API_URL}/diagnostics/hosted-scanner-runtime`, {cache: "no-store"});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.error || `Runtime diagnostics failed with ${response.status}`);
      setData(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Runtime diagnostics failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDiagnostics();
  }, []);

  const tools = data?.tools || [];
  const byCategory = ["runtime", "dependency", "static", "secret"].map((category) => ({
    category,
    tools: tools.filter((tool) => tool.category === category),
  }));

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO hosted scanner diagnostics</p>
        <h1>Scanner Runtime Verification</h1>
        <p className="lead">This page checks deployed container tool availability. It does not mark scanner output clean and it does not change scoring.</p>
      </section>

      <section className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">Runtime readiness</p>
            <h2>{data?.summary?.runtime_ready ? "Runtime ready" : data ? "Runtime blockers found" : "Checking runtime"}</h2>
          </div>
          <span className={data?.summary?.runtime_ready ? "status green" : data ? "status yellow" : "status gray"}>{loading ? "loading" : data?.status || "not loaded"}</span>
        </div>
        {error ? <p className="error-box">{error}</p> : null}
        <p className="warning-box">Missing tools stay unavailable evidence. This page only proves deployment/runtime availability.</p>
        <div className="grid three inset-grid">
          <article><b>Installed scanner tools</b><span>{data?.summary?.installed_count ?? 0}</span></article>
          <article><b>Missing scanner tools</b><span>{data?.summary?.missing_count ?? 0}</span></article>
          <article><b>Required scanner tools</b><span>{data?.summary?.required_scanner_tool_count ?? 0}</span></article>
        </div>
        <button type="button" className="primary-button" disabled={loading || !API_URL} onClick={loadDiagnostics}>{loading ? "Checking..." : "Refresh runtime diagnostics"}</button>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Blockers</p><h2>What prevents scanner execution</h2></div><span className={data?.blockers?.length ? "status yellow" : "status green"}>{data?.blockers?.length || 0}</span></div>
        <ListBlock items={data?.blockers} />
      </section>

      {byCategory.map((group) => (
        <section className="section panel" key={group.category}>
          <div className="section-head"><div><p className="eyebrow">{group.category}</p><h2>{group.category} tools</h2></div><span className="status blue">{group.tools.length}</span></div>
          <div className="results-grid">
            {group.tools.map((tool) => (
              <article className="result-card" key={tool.tool}>
                <div className="result-head"><b>{tool.tool}</b><span className={statusClass(tool.status, tool.installed)}>{tool.status}</span></div>
                <p><b>Binary:</b> {tool.binary}</p>
                <p><b>Path:</b> {tool.path || "not found"}</p>
                <p><b>Version:</b> {tool.version || "unknown"}</p>
                <p><b>Required for:</b> {tool.required_for}</p>
                <p><b>Return code:</b> {tool.returncode ?? "n/a"}</p>
                {tool.reason ? <p><b>Reason:</b> {tool.reason}</p> : null}
              </article>
            ))}
          </div>
        </section>
      ))}

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Environment</p><h2>Hosted configuration</h2></div><span className="status gray">read only</span></div>
        <div className="results-grid">
          {Object.entries(data?.config || {}).map(([key, value]) => <article className="result-card" key={key}><b>{key}</b><p>{String(value)}</p></article>)}
        </div>
        <p className="muted">Generated at: {data?.generated_at || "not loaded"}</p>
        <p className="muted">{data?.guardrail || "No guardrail returned yet."}</p>
      </section>
    </main>
  );
}
