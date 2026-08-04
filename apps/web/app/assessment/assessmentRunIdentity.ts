import type {Result} from "./assessmentTypes";

export type RunIdentityFallback = {
  runId: string;
  repository?: string;
  customerId?: string;
  projectId?: string;
  commitSha?: string;
  evidenceLedgerId?: string;
};

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function preserveRunIdentity(
  value: Result,
  fallback: RunIdentityFallback,
): Result {
  const record = objectRecord(value.record);
  const identity = objectRecord(record.identity);
  const runId = String(
    value.run_id || identity.run_id || fallback.runId || "",
  ).trim();
  const repository = String(
    value.repository || identity.repository || fallback.repository || "",
  ).trim();
  const customerId = String(
    value.customer_id ||
      identity.customer_id ||
      fallback.customerId ||
      "default_customer",
  ).trim();
  const projectId = String(
    value.project_id ||
      identity.project_id ||
      fallback.projectId ||
      "default_project",
  ).trim();
  const commitSha = String(
    value.commit_sha ||
      identity.commit_sha ||
      value.repository_snapshot?.commit_sha ||
      fallback.commitSha ||
      "",
  ).trim();
  const evidenceLedgerId = String(
    value.evidence_ledger_id ||
      identity.evidence_ledger_id ||
      fallback.evidenceLedgerId ||
      "",
  ).trim();

  return {
    ...value,
    ...(runId ? {run_id: runId} : {}),
    ...(repository ? {repository} : {}),
    ...(customerId ? {customer_id: customerId} : {}),
    ...(projectId ? {project_id: projectId} : {}),
    ...(commitSha ? {commit_sha: commitSha} : {}),
    ...(evidenceLedgerId ? {evidence_ledger_id: evidenceLedgerId} : {}),
    record: {
      ...record,
      identity: {
        ...identity,
        ...(runId ? {run_id: runId} : {}),
        ...(repository ? {repository} : {}),
        ...(customerId ? {customer_id: customerId} : {}),
        ...(projectId ? {project_id: projectId} : {}),
        ...(commitSha ? {commit_sha: commitSha} : {}),
        ...(evidenceLedgerId ? {evidence_ledger_id: evidenceLedgerId} : {}),
      },
    },
  };
}
