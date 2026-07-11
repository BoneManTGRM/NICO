"use client";

import {useState} from "react";
import type {ReactNode} from "react";
import DeliveryLedger from "./DeliveryLedger";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

export default function FullRunLayout({children}: {children: ReactNode}) {
  const [runId, setRunId] = useState("");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [adminToken, setAdminToken] = useState("");
  const [actor, setActor] = useState("owner");

  return <>
    {children}
    <div className="shell">
      <section className="section panel">
        <div className="section-head">
          <div><p className="eyebrow">Delivery operations</p><h2>Owner ledger console</h2></div>
          <span className={API_URL ? "status green" : "status red"}>{API_URL ? "backend configured" : "backend missing"}</span>
        </div>
        <p className="warning-box">Use the exact Full Assessment run ID or report ID and matching customer/project scope. The admin token remains in this browser state only and is never included in ledger exports.</p>
        <div className="form-grid">
          <label>Run or report ID<input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="fullrun_... or report_..." /></label>
          <label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label>
          <label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label>
          <label>Owner / admin identity<input value={actor} onChange={(event) => setActor(event.target.value)} /></label>
          <label>NICO admin token<input type="password" autoComplete="off" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} /></label>
        </div>
        <DeliveryLedger
          apiUrl={API_URL}
          runId={runId.trim()}
          customerId={customerId.trim() || "default_customer"}
          projectId={projectId.trim() || "default_project"}
          adminToken={adminToken}
          actor={actor.trim() || "owner"}
          disabled={!API_URL || !runId.trim()}
        />
      </section>
    </div>
  </>;
}
