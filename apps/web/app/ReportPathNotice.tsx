type ReportPathConflict = {
  detected?: boolean;
  expected?: string;
  observed?: string[];
  message?: string;
};

type ReportPathNoticeProps = {
  expectedPath: "express" | "full_run";
  reportPath?: string;
  reportPathLabel?: string;
  conflict?: ReportPathConflict | null;
  clientReady?: boolean;
};

const labels: Record<ReportPathNoticeProps["expectedPath"], string> = {
  express: "Express Assessment",
  full_run: "Full Assessment",
};

export function reportPathConflictDetected(conflict?: ReportPathConflict | null) {
  return Boolean(conflict?.detected);
}

export default function ReportPathNotice({expectedPath, reportPath, reportPathLabel, conflict, clientReady}: ReportPathNoticeProps) {
  const hasConflict = reportPathConflictDetected(conflict);
  const effectivePath = reportPath || expectedPath;
  const effectiveLabel = reportPathLabel || labels[expectedPath];

  if (hasConflict) {
    return <div className="error-box" role="alert" aria-live="assertive">
      <b>Report-path conflict detected</b>
      <p>{conflict?.message || "The report origin does not match this assessment path."}</p>
      <p><b>Expected:</b> {conflict?.expected || expectedPath}</p>
      <p><b>Observed:</b> {(conflict?.observed || []).join(", ") || "unknown"}</p>
      <p>Client delivery actions are disabled until a human verifies the report origin.</p>
    </div>;
  }

  return <div className="summary-box" role="status">
    <b>Report path:</b> {effectiveLabel} (<code>{effectivePath}</code>).
    {clientReady === true ? " Human approval evidence marks this result client-ready." : " Human review remains required before client delivery."}
  </div>;
}
