"use client";

import {useEffect, useMemo, useState} from "react";
import {API, getJSON, postJSON} from "../lib/api";

type ViewKey = "dashboard" | "findings" | "drift" | "repairs" | "verification" | "memory" | "reports" | "policy" | "audit" | "scan";

type AppData = {
  health: any;
  latestScan: any;
  findings: any[];
  drift: any[];
  repairs: any[];
  verification: any;
  memory: any[];
  reports: any[];
  latestReport: any;
  policy: any;
  audit: any[];
};

const emptyData: AppData = {
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

const navItems: {key: ViewKey; label: string}[] = [
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

function asArray(value: any): any[] {
  return Array.isArray(value) ? value : [];
}

function countBySeverity(findings: any[]) {
  return findings.reduce((acc: Record<string, number>, finding: any) => {
    const key = String(finding?.severity || "unknown").toLowerCase();
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function Card({children, className = ""}: {children: any; className?: string}) {
  return <section className={`card ${className}`}>{children}</section>;
}

function Button(props: any) {
  const {className = "", primary, danger, ...rest} = props;
  return <button className={`btn ${primary ? "primary" : ""} ${danger ? "danger" : ""} ${className}`} {...rest}>{props.children}</button>;
}

function Badge({children, tone = "low"}: {children: any; tone?: string}) {
  return <span className={`badge ${String(tone || "low").toLowerCase()}`}>{children}</span>;
}

function EmptyState({children}: {children: any}) {
  return <div className="empty">{children}</div>;
}

function JsonBlock({value}: {value: any}) {
  return <pre>{JSON.stringify(value ?? {}, null, 2)}</pre>;
}

function Sidebar({view, setView}: {view: ViewKey; setView: (view: ViewKey) => void}) {
  return (
    <aside className="sidebar">
      <div className="brand">NICO</div>
      <div className="tag">Neural Intelligence Cyber Operations</div>
      <nav className="nav" aria-label="NICO sections">
        {navItems.map((item) => (
          <button key={item.key} className={view === item.key ? "active" : ""} onClick={() => setView(item.key)}>
            {item.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}

function Metric({label, value, detail}: {label: string; value: any; detail?: string}) {
  return (
    <Card>
      <div className="muted">{label}</div>
      <div className="metric">{value}</div>
      {detail ? <div className="fine">{detail}</div> : null}
    </Card>
  );
}

function FindingsTable({items}: {items: any[]}) {
  if (!items.length) return <EmptyState>No findings yet. Run a scan to populate this table.</EmptyState>;
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Severity</th>
            <th>Category</th>
            <th>Title</th>
            <th>File</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {items.slice(0, 80).map((finding: any, index: number) => (
            <tr key={finding?.id || index}>
              <td><Badge tone={finding?.severity}>{finding?.severity || "unknown"}</Badge></td>
              <td>{finding?.category || "-"}</td>
              <td>{finding?.title || finding?.description || "Untitled finding"}</td>
              <td>{finding?.file_path || finding?.affected_file || "-"}</td>
              <td className="evidence">{finding?.masked_evidence || finding?.evidence || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RepairsTable({items}: {items: any[]}) {
  if (!items.length) return <EmptyState>No repair plans yet. Run a scan first, then export/verify as needed.</EmptyState>;
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Status</th>
            <th>Finding</th>
            <th>Repair</th>
            <th>Verification</th>
          </tr>
        </thead>
        <tbody>
          {items.slice(0, 80).map((repair: any, index: number) => (
            <tr key={repair?.id || index}>
              <td><Badge tone="medium">{repair?.status || "planned"}</Badge></td>
              <td>{repair?.finding_id || repair?.category || "-"}</td>
              <td>{repair?.recommendation || repair?.repair || repair?.exact_issue || "Repair details unavailable"}</td>
              <td>{repair?.verification_command || repair?.verification || "Manual verification required"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Dashboard({data, refresh}: {data: AppData; refresh: () => void}) {
  const severity = useMemo(() => countBySeverity(data.findings), [data.findings]);
  const latestStatus = data.latestScan?.payload?.status || data.latestScan?.kind || "No scan yet";
  return (
    <>
      <div className="grid metrics">
        <Metric label="API" value={data.health?.status || "offline"} detail={data.health?.mode || API} />
        <Metric label="Findings" value={data.findings.length} detail={`Critical ${severity.critical || 0} · High ${severity.high || 0}`} />
        <Metric label="Repairs" value={data.repairs.length} detail="Generated repair plans" />
        <Metric label="Autonomy" value={`L${data.policy?.autonomy_level ?? 1}`} detail={data.policy?.kill_switch ? "Kill switch on" : "Local safe mode"} />
      </div>

      <div className="section twoCol">
        <Card>
          <div className="cardHeader">
            <h2>Operator Actions</h2>
            <Button onClick={refresh}>Refresh</Button>
          </div>
          <div className="actionGrid">
            <Button primary onClick={async () => { await postJSON("/scan/test-lab"); await refresh(); }}>Run Test Lab Scan</Button>
            <Button onClick={async () => { await postJSON("/scan/drift-demo"); await refresh(); }}>Run Drift Demo</Button>
            <Button onClick={async () => { await postJSON("/reports/generate"); await refresh(); }}>Generate Reports</Button>
            <Button onClick={async () => { await postJSON("/verification/latest"); await refresh(); }}>Verify Latest</Button>
          </div>
        </Card>

        <Card>
          <h2>System State</h2>
          <div className="stateList">
            <div><span>Latest scan</span><strong>{latestStatus}</strong></div>
            <div><span>Drift events</span><strong>{data.drift.length}</strong></div>
            <div><span>Reports</span><strong>{data.reports.length}</strong></div>
            <div><span>Audit records</span><strong>{data.audit.length}</strong></div>
          </div>
        </Card>
      </div>

      <div className="section">
        <Card>
          <h2>Latest Findings</h2>
          <FindingsTable items={data.findings.slice(0, 10)} />
        </Card>
      </div>
    </>
  );
}

function ScanView({refresh}: {refresh: () => void}) {
  const [path, setPath] = useState(".");
  const [message, setMessage] = useState("");

  async function runAction(label: string, action: () => Promise<any>) {
    setMessage(`${label} started...`);
    try {
      await action();
      await refresh();
      setMessage(`${label} completed.`);
    } catch (error: any) {
      setMessage(`${label} failed: ${error?.message || String(error)}`);
    }
  }

  return (
    <Card>
      <h2>Run Scans</h2>
      <p className="muted">Use safe local scan actions only. The local path is evaluated by the NICO API process, not by this browser.</p>
      <div className="actionGrid">
        <Button primary onClick={() => runAction("Test lab scan", () => postJSON("/scan/test-lab"))}>Run Test Lab Scan</Button>
        <Button onClick={() => runAction("Drift demo", () => postJSON("/scan/drift-demo"))}>Run Drift Demo</Button>
      </div>
      <div className="formRow">
        <label>
          Local path
          <input value={path} onChange={(event) => setPath(event.target.value)} placeholder="/path/to/authorized/project" />
        </label>
        <Button onClick={() => runAction("Local scan", () => postJSON("/scan/local", {path}))}>Run Local Scan</Button>
      </div>
      {message ? <div className="notice">{message}</div> : null}
    </Card>
  );
}

function ReportsView({data, refresh}: {data: AppData; refresh: () => void}) {
  return (
    <div className="sectionStack">
      <Card>
        <div className="cardHeader">
          <h2>Reports</h2>
          <Button primary onClick={async () => { await postJSON("/reports/generate"); await refresh(); }}>Generate Reports</Button>
        </div>
        {data.reports.length ? (
          <div className="tableWrap">
            <table>
              <thead><tr><th>Format</th><th>Path</th><th>Created</th></tr></thead>
              <tbody>{data.reports.slice(0, 40).map((report: any, index: number) => <tr key={index}><td>{report?.format || "-"}</td><td>{report?.path || "-"}</td><td>{report?.created_at || "-"}</td></tr>)}</tbody>
            </table>
          </div>
        ) : <EmptyState>No reports yet. Generate reports after a scan.</EmptyState>}
      </Card>
      <Card>
        <h2>Latest Report Metadata</h2>
        <JsonBlock value={data.latestReport} />
      </Card>
    </div>
  );
}

export default function Page() {
  const [view, setView] = useState<ViewKey>("dashboard");
  const [data, setData] = useState<AppData>(emptyData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [health, latestScan, findings, drift, repairs, verification, memory, reports, latestReport, policy, audit] = await Promise.all([
        getJSON("/health").catch((err) => ({status: "offline", error: String(err?.message || err)})),
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
      setData({health, latestScan, findings: asArray(findings), drift: asArray(drift), repairs: asArray(repairs), verification, memory: asArray(memory), reports: asArray(reports), latestReport, policy, audit: asArray(audit)});
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  let content: any = null;
  if (view === "dashboard") content = <Dashboard data={data} refresh={load} />;
  if (view === "scan") content = <ScanView refresh={load} />;
  if (view === "findings") content = <Card><h2>Findings</h2><FindingsTable items={data.findings} /></Card>;
  if (view === "repairs") content = <Card><h2>Repair Queue</h2><RepairsTable items={data.repairs} /></Card>;
  if (view === "drift") content = <Card><h2>Drift Events</h2>{data.drift.length ? <JsonBlock value={data.drift} /> : <EmptyState>No drift events yet.</EmptyState>}</Card>;
  if (view === "verification") content = <Card><h2>Verification</h2><JsonBlock value={data.verification} /></Card>;
  if (view === "memory") content = <Card><h2>Repair Memory</h2>{data.memory.length ? <JsonBlock value={data.memory} /> : <EmptyState>No repair memory yet.</EmptyState>}</Card>;
  if (view === "reports") content = <ReportsView data={data} refresh={load} />;
  if (view === "policy") content = <Card><h2>Policy</h2><JsonBlock value={data.policy} /></Card>;
  if (view === "audit") content = <Card><h2>Audit Log</h2>{data.audit.length ? <JsonBlock value={data.audit} /> : <EmptyState>No audit records yet.</EmptyState>}</Card>;

  return (
    <div className="shell">
      <Sidebar view={view} setView={setView} />
      <main className="main">
        <div className="topbar">
          <div>
            <h1>NICO Command Center</h1>
            <div className="muted">Local-first defensive cyber operations · API: {API}</div>
          </div>
          <div className="topActions">
            {loading ? <span className="fine">Loading...</span> : null}
            <Button onClick={load}>Refresh</Button>
            <Badge tone={data.health?.status === "ok" ? "low" : "high"}>{data.health?.status || "unknown"}</Badge>
          </div>
        </div>
        {error ? <div className="notice dangerNotice">{error}</div> : null}
        {content}
      </main>
    </div>
  );
}
