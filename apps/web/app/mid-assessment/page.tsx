"use client";

import Link from "next/link";
import {useMemo, useState} from "react";

import {
  MID_STAGE_DEFINITIONS,
  MidIdentityPanel,
  useMidWorkspace,
  type MidStage,
} from "../MidWorkspaceContext";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type StageState = "not_checked" | "needs_run" | "ready" | "pending" | "approved" | "delivered" | "unavailable";

type StageResult = {
  state: StageState;
  summary: string;
  evidence?: string[];
};

type WorkspaceStatus = Record<MidStage, StageResult>;

type ApprovalPayload = {
  approval?: {
    status?: string;
    draft_report_id?: string;
    approved?: boolean;
    approved_report?: {report_id?: string};
  };
};

function initialStatus(runId: string): WorkspaceStatus {
  return {
    start: {
      state: runId.startsWith("midrun_") ? "ready" : "needs_run",
      summary: runId.startsWith("midrun_") ? `Exact run selected: ${runId}` : "Start a Mid assessment or enter an existing midrun ID.",
    },
    review: {state: "not_checked", summary: "Review status has not been checked."},
    report: {state: "not_checked", summary: "Draft report status has not been checked."},
    approval: {state: "not_checked", summary: "Approval status has not been checked."},
    delivery: {state: "not_checked", summary: "Delivery grants and receipts have not been checked."},
  };
}

function badgeClass(state: StageState) {
  if (["ready", "approved", "delivered"].includes(state)) return "status green";
  if (["pending", "not_checked"].includes(state)) return "status yellow";
  if (["needs_run", "unavailable"].includes(state)) return "status gray";
  return "status gray";
}

async function safeJson(response: Response): Promise<Record<string, unknown> | null> {
  try {
    return await response.json() as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function MidAssessmentWorkspacePage() {
  const {
    runId,
    customerId,
    projectId,
    adminToken,
    buildHref,
    identityReady,
  } = useMidWorkspace();
  const [status, setStatus] = useState<WorkspaceStatus>(() => initialStatus(runId));
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const stageMap = useMemo(() => new Map(MID_STAGE_DEFINITIONS.map((stage) => [stage.key, stage])), []);

  async function refreshStatus() {
    if (!API_URL || !identityReady || !adminToken.trim() || loading) return;
    setLoading(true);
    setMessage("");

    const params = new URLSearchParams({
      customer_id: customerId.trim() || "default_customer",
      project_id: projectId.trim() || "default_project",
    });
    const headers = {"X-NICO-Admin-Token": adminToken};
    const encodedRun = encodeURIComponent(runId.trim());

    try {
      const [reviewResponse, approvalResponse, accessResponse, receiptsResponse] = await Promise.all([
        fetch(`${API_URL}/assessment/mid-run/${encodedRun}/review-exceptions?${params.toString()}`, {headers, cache: "no-store"}),
        fetch(`${API_URL}/assessment/mid-run/${encodedRun}/approval?${params.toString()}`, {headers, cache: "no-store"}),
        fetch(`${API_URL}/assessment/mid-run/${encodedRun}/delivery/access?${params.toString()}`, {headers, cache: "no-store"}),
        fetch(`${API_URL}/assessment/mid-run/${encodedRun}/delivery/receipts?${params.toString()}`, {headers, cache: "no-store"}),
      ]);

      const reviewData = await safeJson(reviewResponse);
      const approvalData = await safeJson(approvalResponse) as ApprovalPayload | null;
      const accessData = await safeJson(accessResponse) as {access?: Array<{status?: string}>} | null;
      const receiptsData = await safeJson(receiptsResponse) as {receipts?: unknown[]} | null;

      const reviewSummary = reviewData?.summary as {items_requiring_review?: number; sections_verified?: number} | undefined;
      const reviewReady = reviewResponse.ok && String(reviewData?.status || "") === "ready_for_review";
      const approval = approvalResponse.ok ? approvalData?.approval : undefined;
      const approved = Boolean(approval?.approved || approval?.status === "approved" || approval?.approved_report?.report_id);
      const draftExists = Boolean(approval?.draft_report_id || approval?.approved_report?.report_id);
      const grants = accessResponse.ok && Array.isArray(accessData?.access) ? accessData.access : [];
      const receipts = receiptsResponse.ok && Array.isArray(receiptsData?.receipts) ? receiptsData.receipts : [];
      const activeGrants = grants.filter((item) => item?.status === "active").length;

      setStatus({
        start: {state: "ready", summary: `Exact run selected: ${runId}`},
        review: reviewReady
          ? {
              state: "ready",
              summary: `${reviewSummary?.items_requiring_review ?? 0} exception items require human review.`,
              evidence: [`Verified sections: ${reviewSummary?.sections_verified ?? 0}`],
            }
          : {
              state: reviewResponse.status === 404 ? "pending" : "unavailable",
              summary: reviewResponse.status === 404 ? "The run is not ready for review yet." : "Review status could not be verified.",
            },
        report: draftExists
          ? {state: "ready", summary: `Bound draft artifact: ${approval?.draft_report_id || approval?.approved_report?.report_id}`}
          : reviewReady
          ? {state: "pending", summary: "Review packet is ready; the automated draft should be verified in the Report stage."}
          : {state: "not_checked", summary: "Draft status cannot be inferred until review or approval evidence is available."},
        approval: approved
          ? {state: "approved", summary: `Approved artifact: ${approval?.approved_report?.report_id || "recorded"}`}
          : approvalResponse.ok
          ? {state: "pending", summary: `Approval state: ${approval?.status || "requested"}`}
          : {
              state: approvalResponse.status === 404 ? "pending" : "unavailable",
              summary: approvalResponse.status === 404 ? "Approval has not been requested." : "Approval status could not be verified.",
            },
        delivery: receipts.length
          ? {state: "delivered", summary: `${receipts.length} acknowledged download receipt${receipts.length === 1 ? "" : "s"} recorded.`}
          : activeGrants
          ? {state: "pending", summary: `${activeGrants} active delivery grant${activeGrants === 1 ? "" : "s"}; no receipt recorded yet.`}
          : accessResponse.ok && receiptsResponse.ok
          ? {state: approved ? "pending" : "not_checked", summary: approved ? "Approved artifact has no active delivery grant." : "Delivery remains unavailable until approval."}
          : {state: "unavailable", summary: "Delivery status could not be verified."},
      });
      setMessage("Workspace status refreshed from read-only Mid review, approval, grant, and receipt endpoints. No report, approval, grant, or delivery mutation was performed.");
    } catch {
      setMessage("Workspace status refresh failed. No Mid workflow mutation was performed.");
    } finally {
      setLoading(false);
    }
  }

  return <main className="shell">
    <section className="hero">
      <p className="eyebrow">NICO Mid Assessment</p>
      <h1>Advanced review workspace</h1>
      <p className="lead">Normal Mid assessments start from the unified one-click intake. This compatibility workspace is for reviewing an existing exact run through Review, Report verification, Approval, and Delivery.</p>
      <div className="hero-actions">
        <Link className="primary-link" href="/assessment?tier=mid#assessment">Start a new Mid assessment</Link>
        <button type="button" disabled={!API_URL || !identityReady || !adminToken.trim() || loading} onClick={refreshStatus}>{loading ? "Checking exact state..." : "Refresh workspace status"}</button>
      </div>
      {message ? <p className="summary-box">{message}</p> : null}
    </section>

    <MidIdentityPanel title="Select one Mid run for every advanced stage" />

    <section className="section panel">
      <div className="section-head">
        <div><p className="eyebrow">Guarded workflow</p><h2>Start → Review → Report → Approval → Delivery</h2></div>
        <span className={identityReady ? "status green" : "status gray"}>{identityReady ? "identity bound" : "run required"}</span>
      </div>
      <div className="mid-workspace-grid">
        {MID_STAGE_DEFINITIONS.map((stage) => {
          const stageStatus = status[stage.key];
          const href = stage.key === "start" ? stage.path : buildHref(stage.path);
          return <article className="result-card mid-workspace-stage" key={stage.key} data-stage={stage.key}>
            <div className="result-head"><b>{stage.label}</b><span className={badgeClass(stageStatus.state)}>{stageStatus.state.replaceAll("_", " ")}</span></div>
            <p>{stage.description}</p>
            <p className="muted">{stageStatus.summary}</p>
            {stageStatus.evidence?.length ? <ul className="tight-list">{stageStatus.evidence.map((item) => <li key={item}>{item}</li>)}</ul> : null}
            <Link className="secondary-link" href={href}>{stage.key === "start" ? "Open unified Mid intake" : `Open ${stageMap.get(stage.key)?.label || stage.label}`}</Link>
          </article>;
        })}
      </div>
    </section>

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Control boundary</p><h2>Passive refresh is read-only</h2></div><span className="status blue">Human controlled</span></div>
      <ul className="tight-list">
        <li>The unified Mid intake automatically performs evidence collection, scanner continuation, draft generation, and review-request creation.</li>
        <li>This workspace status refresh uses only existing review, approval-status, grant-list, and receipt-list GET endpoints.</li>
        <li>Item dispositions and final approval happen only in Approval.</li>
        <li>Private delivery access happens only in Delivery after approval.</li>
        <li>The admin token remains in memory and is never added to links or browser storage.</li>
      </ul>
    </section>
  </main>;
}
