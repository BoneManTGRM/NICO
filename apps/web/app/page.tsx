"use client";

import {useEffect, useState} from "react";
import type {ButtonHTMLAttributes, ReactNode} from "react";
import {API, getJSON, postJSON} from "../lib/api";

type View = "dashboard" | "scan" | "findings" | "repairs" | "drift" | "verification" | "reports" | "policy" | "memory" | "audit";

type State = {
  health: Record<string, unknown>;
  latestScan: Record<string, unknown>;
  findings: unknown[];
  drift: unknown[];
  repairs: unknown[];
  verification: Record<string, unknown>;
  memory: unknown[];
  reports: unknown[];
  latestReport: Record<string, unknown>;
  policy: Record<string, unknown>;
  audit: unknown[];
};

const initialState: State = {
  health: {},
  latestScan: {},
  findings: [],
  drift: [],
  repairs: [],
  verification: {},
  memory: [],
  reports: [],
  latestReport: {},
  policy: {},
  audit: [],
};

const views: {key: View; label: string}[] = [
  {key: "dashboard", label: "Mission Control"},
  {key: "scan", label: "Run Scans"},
  {key: "findings", label: "Findings"},
  {key: "repairs", label: "Repairs"},
  {key: "drift", label: "Drift"},
  {key: "verification", label: "Verification"},
  {key: "reports", label: "Reports"},
  {key: "policy", label: "Policy"},
  {key: "memory", label: "Memory"},
  {key: "audit", label: "Audit Log"},
];

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function field(item: unknown, key: string): string {
  const object = asObject(item);
  const value = object[key];
  return value === undefined || value === null || value === "" ? "-" : String(value);
}

function Card({title, children}: {title?: string; children: ReactNode}) {
  return <section className="card">{title ? <h2>{title}</h2> : null}{children}</section>;
}

type ActionButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {primary?: boolean};
function ActionButton({children, primary, className = "", ...props}: ActionButtonProps) {
  return <button className={`btn ${primary ? "primary" : ""} ${className}`} {...props}>{children}</button>;
}

function Badge({children, tone = "low"}: {children: ReactNode; tone?: string}) {
  return <span className={`badge ${tone.toLowerCase()}`}>{children}</span>;
}

function Empty({children}: {children: ReactNode}) {
  return <div className="empty">{children}</div>;
}

function Json({value}: {value: unknown}) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}

function Sidebar({view, setView}: {view: View; setView: (view: View) => void}) {
  return (
    <aside className="sidebar">
      <div className="brand">NICO</div>
      <div className="tag">Neural Intelligence Cyber Operations</div>
      <nav className="nav" aria-label="NICO navigation">
        {views.map((item) => (
          <button key={item.key} className={view === item.key ? "active" : ""} onClick={() => setView(item.key)}>
            {item.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}

function Metric({label, value, detail}: {label: string; value: string | number; detail?: string}) {
  return (
    <Card>
      <div className="muted">{label}</div>
      <div className="metric">{value}</div>
      {detail ? <div className="fine">{detail}</div> : null}
    </Card>
  );
}

function FindingsTable({items}: {items: unknown[]}) {
  if (!items.length) return <Empty>No findings yet. Run a scan to populate this table.</Empty>;
  return (
    <div className="tableWrap">
      <table>
        <thead><tr><th>Severity</th><th>Category</th><th>Title</th><th>File</th><th>Evidence</th></tr></thead>
        <tbody>
          {items.slice(0, 80).map((item, index) => {
            const severity = field(item, "severity");
            return (
              <tr key={`${field(item, "id")}-${index}`}>
                <td><Badge tone={severity}>{severity}</Badge></td>
                <td>{field(item, "category")}</td>
                <td>{field(item, "title") !== "-" ? field(item, "title") : field(item, "description")}</td>
                <td>{field(item, "file_path") !== "-" ? field(item, "file_path") : field(item, "affected_file")}</td>
                <td className="evidence">{field(item, "masked_evidence") !== "-" ? field(item, "masked_evidence") : field(item, "evidence")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RepairsTable({items}: {items: unknown[]}) {
  if (!items.length) return <Empty>No repair plans yet. Run a scan first.</Empty>;
  return (
    <div className="tableWrap">
      <table>
        <thead><tr><th>Status</th><th>Finding</th><th>Repair</th><th>Verification</th></tr></thead>
        <tbody>
          {items.slice(0, 80).map((item, index) => (
            <tr key={`${field(item, "id")}-${index}`}>
              <td><Badge tone="medium">{field(item, "status")}</Badge></td>
              <td>{field(item, "finding_id") !== "-" ? field(item, "finding_id") : field(item, "category")}</td>
              <td>{field(item, "recommendation") !== "-" ? field(item, "recommendation") : field(item, "repair")}</td>
              <td>{field(item, "verification_command") !== "-" ? field(item, "verification_command") : "Manual verification required"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Page() {
  const [view, setView] = useState<View>("dashboard");
  const [data, setData] = useState<State>(initialState);
  const [localPath, setLocalPath] = useState(".");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    const [health, latestScan, findings, drift, repairs, verification, memory, reports, latestReport, policy, audit] = await Promise.all([
      getJSON("/health").catch((error) => ({status: "offline", error: String(error?.message || error)})),
      getJSON("/scans/latest").catch(() => ({})),
      getJSON("/findings").catch(() => []),
      getJSON("/drift").catch(() => []),
      getJSON("/repairs").catch(() => []),
      getJSON("/verification/latest").catch(() => ({})),
      getJSON("/memory").catch(() => []),
      getJSON("/reports").catch(() => []),
      getJSON("/reports/latest").catch(() => ({})),
      getJSON("/policy").catch(() => ({})),
      getJSON("/audit-log").catch(() => []),
    ]);
    setData({
      health: asObject(health),
      latestScan: asObject(latestScan),
      findings: asArray(findings),
      drift: asArray(drift),
      repairs: asArray(repairs),
      verification: asObject(verification),
      memory: asArray(memory),
      reports: asArray(reports),
      latestReport: asObject(latestReport),
      policy: asObject(policy),
      audit: asArray(audit),
    });
    setLoading(false);
  }

  async function runAction(label: string, action: () => Promise<unknown>) {
    setNotice(`${label} started...`);
    try {
      await action();
      await load();
      setNotice(`${label} completed.`);
    } catch (error: unknown) {
      setNotice(`${label} failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  useEffect(() => { void load(); }, []);

  const healthStatus = String(data.health.status || "unknown");
  const autonomy = String(data.policy.autonomy_level || 1);

  return (
    <div className="shell">
      <Sidebar view={view} setView={setView} />
      <main className="main">
        <div className="topbar">
          <div>
            <h1>NICO Command Center</h1>
            <div className="muted">Local-first operator UI · API: {API}</div>
          </div>
          <div className="topActions">
            {loading ? <span className="fine">Loading...</span> : null}
            <ActionButton onClick={() => { void load(); }}>Refresh</ActionButton>
            <Badge tone={healthStatus === "ok" ? "low" : "high"}>{healthStatus}</Badge>
          </div>
        </div>

        {notice ? <div className="notice">{notice}</div> : null}

        {view === "dashboard" ? (
          <>
            <div className="grid metrics">
              <Metric label="API" value={healthStatus} detail={String(data.health.mode || "local")} />
              <Metric label="Findings" value={data.findings.length} detail="Current stored findings" />
              <Metric label="Repairs" value={data.repairs.length} detail="Current repair plans" />
              <Metric label="Autonomy" value={`L${autonomy}`} detail="Policy level" />
            </div>
            <div className="section twoCol">
              <Card title="Operator Actions">
                <div className="actionGrid">
                  <ActionButton primary onClick={() => { void runAction("Test lab scan", () => postJSON("/scan/test-lab")); }}>Run Test Lab Scan</ActionButton>
                  <ActionButton onClick={() => { void runAction("Drift demo", () => postJSON("/scan/drift-demo")); }}>Run Drift Demo</ActionButton>
                  <ActionButton onClick={() => { void runAction("Generate reports", () => postJSON("/reports/generate")); }}>Generate Reports</ActionButton>
                  <ActionButton onClick={() => { void runAction("Verify latest", () => postJSON("/verification/latest")); }}>Verify Latest</ActionButton>
                </div>
              </Card>
              <Card title="System State">
                <div className="stateList">
                  <div><span>Drift events</span><strong>{data.drift.length}</strong></div>
                  <div><span>Reports</span><strong>{data.reports.length}</strong></div>
                  <div><span>Audit records</span><strong>{data.audit.length}</strong></div>
                </div>
              </Card>
            </div>
            <div className="section"><Card title="Latest Findings"><FindingsTable items={data.findings.slice(0, 10)} /></Card></div>
          </>
        ) : null}

        {view === "scan" ? (
          <Card title="Run Scans">
            <p className="muted">Only scan systems and paths you are authorized to assess. The local path is evaluated by the NICO API process.</p>
            <div className="actionGrid">
              <ActionButton primary onClick={() => { void runAction("Test lab scan", () => postJSON("/scan/test-lab")); }}>Run Test Lab Scan</ActionButton>
              <ActionButton onClick={() => { void runAction("Drift demo", () => postJSON("/scan/drift-demo")); }}>Run Drift Demo</ActionButton>
            </div>
            <div className="formRow">
              <label>Local path<input value={localPath} onChange={(event) => setLocalPath(event.target.value)} /></label>
              <ActionButton onClick={() => { void runAction("Local scan", () => postJSON("/scan/local", {path: localPath})); }}>Run Local Scan</ActionButton>
            </div>
          </Card>
        ) : null}

        {view === "findings" ? <Card title="Findings"><FindingsTable items={data.findings} /></Card> : null}
        {view === "repairs" ? <Card title="Repair Queue"><RepairsTable items={data.repairs} /></Card> : null}
        {view === "drift" ? <Card title="Drift Events">{data.drift.length ? <Json value={data.drift} /> : <Empty>No drift events yet.</Empty>}</Card> : null}
        {view === "verification" ? <Card title="Verification"><Json value={data.verification} /></Card> : null}
        {view === "reports" ? <Card title="Reports"><ActionButton primary onClick={() => { void runAction("Generate reports", () => postJSON("/reports/generate")); }}>Generate Reports</ActionButton>{data.reports.length ? <Json value={data.reports} /> : <Empty>No reports yet.</Empty>}<h2>Latest Report</h2><Json value={data.latestReport} /></Card> : null}
        {view === "policy" ? <Card title="Policy"><Json value={data.policy} /></Card> : null}
        {view === "memory" ? <Card title="Memory">{data.memory.length ? <Json value={data.memory} /> : <Empty>No memory records yet.</Empty>}</Card> : null}
        {view === "audit" ? <Card title="Audit Log">{data.audit.length ? <Json value={data.audit} /> : <Empty>No audit records yet.</Empty>}</Card> : null}
      </main>
    </div>
  );
}
