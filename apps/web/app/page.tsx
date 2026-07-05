"use client";

import {useEffect, useState} from "react";
import {API, getJSON, postJSON} from "../lib/api";

const views = [
  ["dashboard", "Mission Control"],
  ["scan", "Run Scans"],
  ["findings", "Findings"],
  ["repairs", "Repairs"],
  ["drift", "Drift"],
  ["verification", "Verification"],
  ["reports", "Reports"],
  ["policy", "Policy"],
  ["memory", "Memory"],
  ["audit", "Audit Log"],
];

function toArray(value: any) {
  return Array.isArray(value) ? value : [];
}

function valueOf(item: any, key: string) {
  const value = item && typeof item === "object" ? item[key] : undefined;
  return value === undefined || value === null || value === "" ? "-" : String(value);
}

function Card({title, children}: any) {
  return <section className="card">{title ? <h2>{title}</h2> : null}{children}</section>;
}

function Button({children, primary, className = "", ...props}: any) {
  return <button className={`btn ${primary ? "primary" : ""} ${className}`} {...props}>{children}</button>;
}

function Badge({children, tone = "low"}: any) {
  return <span className={`badge ${String(tone || "low").toLowerCase()}`}>{children}</span>;
}

function Empty({children}: any) {
  return <div className="empty">{children}</div>;
}

function Json({value}: any) {
  return <pre>{JSON.stringify(value ?? {}, null, 2)}</pre>;
}

function Sidebar({view, setView}: any) {
  return (
    <aside className="sidebar">
      <div className="brand">NICO</div>
      <div className="tag">Neural Intelligence Cyber Operations</div>
      <nav className="nav" aria-label="NICO navigation">
        {views.map(([key, label]) => (
          <button key={key} className={view === key ? "active" : ""} onClick={() => setView(key)}>
            {label}
          </button>
        ))}
      </nav>
    </aside>
  );
}

function Metric({label, value, detail}: any) {
  return (
    <Card>
      <div className="muted">{label}</div>
      <div className="metric">{value}</div>
      {detail ? <div className="fine">{detail}</div> : null}
    </Card>
  );
}

function FindingsTable({items}: any) {
  const rows = toArray(items);
  if (!rows.length) return <Empty>No findings yet. Run a scan to populate this table.</Empty>;
  return (
    <div className="tableWrap">
      <table>
        <thead><tr><th>Severity</th><th>Category</th><th>Title</th><th>File</th><th>Evidence</th></tr></thead>
        <tbody>
          {rows.slice(0, 80).map((item: any, index: number) => {
            const severity = valueOf(item, "severity");
            return (
              <tr key={`${valueOf(item, "id")}-${index}`}>
                <td><Badge tone={severity}>{severity}</Badge></td>
                <td>{valueOf(item, "category")}</td>
                <td>{valueOf(item, "title") !== "-" ? valueOf(item, "title") : valueOf(item, "description")}</td>
                <td>{valueOf(item, "file_path") !== "-" ? valueOf(item, "file_path") : valueOf(item, "affected_file")}</td>
                <td className="evidence">{valueOf(item, "masked_evidence") !== "-" ? valueOf(item, "masked_evidence") : valueOf(item, "evidence")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RepairsTable({items}: any) {
  const rows = toArray(items);
  if (!rows.length) return <Empty>No repair plans yet. Run a scan first.</Empty>;
  return (
    <div className="tableWrap">
      <table>
        <thead><tr><th>Status</th><th>Finding</th><th>Repair</th><th>Verification</th></tr></thead>
        <tbody>
          {rows.slice(0, 80).map((item: any, index: number) => (
            <tr key={`${valueOf(item, "id")}-${index}`}>
              <td><Badge tone="medium">{valueOf(item, "status")}</Badge></td>
              <td>{valueOf(item, "finding_id") !== "-" ? valueOf(item, "finding_id") : valueOf(item, "category")}</td>
              <td>{valueOf(item, "recommendation") !== "-" ? valueOf(item, "recommendation") : valueOf(item, "repair")}</td>
              <td>{valueOf(item, "verification_command") !== "-" ? valueOf(item, "verification_command") : "Manual verification required"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Page() {
  const [view, setView] = useState("dashboard");
  const [data, setData] = useState<any>({health: {}, findings: [], drift: [], repairs: [], verification: {}, memory: [], reports: [], latestReport: {}, policy: {}, audit: []});
  const [localPath, setLocalPath] = useState(".");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    const [health, findings, drift, repairs, verification, memory, reports, latestReport, policy, audit] = await Promise.all([
      getJSON("/health").catch((error: any) => ({status: "offline", error: String(error?.message || error)})),
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
    setData({health, findings: toArray(findings), drift: toArray(drift), repairs: toArray(repairs), verification, memory: toArray(memory), reports: toArray(reports), latestReport, policy, audit: toArray(audit)});
    setLoading(false);
  }

  async function runAction(label: string, action: any) {
    setNotice(`${label} started...`);
    try {
      await action();
      await load();
      setNotice(`${label} completed.`);
    } catch (error: any) {
      setNotice(`${label} failed: ${error?.message || String(error)}`);
    }
  }

  useEffect(() => { void load(); }, []);

  const healthStatus = String(data.health?.status || "unknown");
  const autonomy = String(data.policy?.autonomy_level || 1);

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
            <Button onClick={() => { void load(); }}>Refresh</Button>
            <Badge tone={healthStatus === "ok" ? "low" : "high"}>{healthStatus}</Badge>
          </div>
        </div>

        {notice ? <div className="notice">{notice}</div> : null}

        {view === "dashboard" ? (
          <>
            <div className="grid metrics">
              <Metric label="API" value={healthStatus} detail={String(data.health?.mode || "local")} />
              <Metric label="Findings" value={data.findings.length} detail="Current stored findings" />
              <Metric label="Repairs" value={data.repairs.length} detail="Current repair plans" />
              <Metric label="Autonomy" value={`L${autonomy}`} detail="Policy level" />
            </div>
            <div className="section twoCol">
              <Card title="Operator Actions">
                <div className="actionGrid">
                  <Button primary onClick={() => { void runAction("Test lab scan", () => postJSON("/scan/test-lab")); }}>Run Test Lab Scan</Button>
                  <Button onClick={() => { void runAction("Drift demo", () => postJSON("/scan/drift-demo")); }}>Run Drift Demo</Button>
                  <Button onClick={() => { void runAction("Generate reports", () => postJSON("/reports/generate")); }}>Generate Reports</Button>
                  <Button onClick={() => { void runAction("Verify latest", () => postJSON("/verification/latest")); }}>Verify Latest</Button>
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
              <Button primary onClick={() => { void runAction("Test lab scan", () => postJSON("/scan/test-lab")); }}>Run Test Lab Scan</Button>
              <Button onClick={() => { void runAction("Drift demo", () => postJSON("/scan/drift-demo")); }}>Run Drift Demo</Button>
            </div>
            <div className="formRow">
              <label>Local path<input value={localPath} onChange={(event: any) => setLocalPath(event.target.value)} /></label>
              <Button onClick={() => { void runAction("Local scan", () => postJSON("/scan/local", {path: localPath})); }}>Run Local Scan</Button>
            </div>
          </Card>
        ) : null}

        {view === "findings" ? <Card title="Findings"><FindingsTable items={data.findings} /></Card> : null}
        {view === "repairs" ? <Card title="Repair Queue"><RepairsTable items={data.repairs} /></Card> : null}
        {view === "drift" ? <Card title="Drift Events">{data.drift.length ? <Json value={data.drift} /> : <Empty>No drift events yet.</Empty>}</Card> : null}
        {view === "verification" ? <Card title="Verification"><Json value={data.verification} /></Card> : null}
        {view === "reports" ? <Card title="Reports"><Button primary onClick={() => { void runAction("Generate reports", () => postJSON("/reports/generate")); }}>Generate Reports</Button>{data.reports.length ? <Json value={data.reports} /> : <Empty>No reports yet.</Empty>}<h2>Latest Report</h2><Json value={data.latestReport} /></Card> : null}
        {view === "policy" ? <Card title="Policy"><Json value={data.policy} /></Card> : null}
        {view === "memory" ? <Card title="Memory">{data.memory.length ? <Json value={data.memory} /> : <Empty>No memory records yet.</Empty>}</Card> : null}
        {view === "audit" ? <Card title="Audit Log">{data.audit.length ? <Json value={data.audit} /> : <Empty>No audit records yet.</Empty>}</Card> : null}
      </main>
    </div>
  );
}
