#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "apps/web/app/assessment/useAssessmentRun.ts"
TEST = ROOT / "tests/test_active_run_identity_recovery_v1.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return source.replace(old, new, 1)


def patch_hook() -> None:
    source = HOOK.read_text(encoding="utf-8")
    if "function preserveRunIdentity(" in source:
        return

    source = replace_once(
        source,
        '''function normalizePersistedRun(value: unknown): PersistedRun | null {''',
        '''type RunIdentityFallback = {
  runId: string;
  repository?: string;
  customerId?: string;
  projectId?: string;
  commitSha?: string;
  evidenceLedgerId?: string;
};

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function preserveRunIdentity(value: Result, fallback: RunIdentityFallback): Result {
  const record = objectRecord(value.record);
  const identity = objectRecord(record.identity);
  const runId = String(value.run_id || identity.run_id || fallback.runId || "").trim();
  const repository = String(value.repository || identity.repository || fallback.repository || "").trim();
  const customerId = String(value.customer_id || identity.customer_id || fallback.customerId || "default_customer").trim();
  const projectId = String(value.project_id || identity.project_id || fallback.projectId || "default_project").trim();
  const commitSha = String(
    value.commit_sha
      || identity.commit_sha
      || value.repository_snapshot?.commit_sha
      || fallback.commitSha
      || "",
  ).trim();
  const evidenceLedgerId = String(value.evidence_ledger_id || identity.evidence_ledger_id || fallback.evidenceLedgerId || "").trim();

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

function normalizePersistedRun(value: unknown): PersistedRun | null {''',
        "identity normalizer",
    )

    source = replace_once(
        source,
        '''  async function recoverRun(runId: string): Promise<Result | null> {
    try {
      return await requestWithRetry(
        `/assessment/comprehensive-run/${encodeURIComponent(runId)}`,
        {method: "GET"},
        copy,
      );
    } catch {
      return null;
    }
  }''',
        '''  async function recoverRun(runId: string, fallback: Partial<RunIdentityFallback> = {}): Promise<Result | null> {
    try {
      const recovered = await requestWithRetry(
        `/assessment/comprehensive-run/${encodeURIComponent(runId)}`,
        {method: "GET"},
        copy,
      );
      return preserveRunIdentity(recovered, {
        runId,
        repository: fallback.repository,
        customerId: fallback.customerId,
        projectId: fallback.projectId,
        commitSha: fallback.commitSha,
        evidenceLedgerId: fallback.evidenceLedgerId,
      });
    } catch {
      return null;
    }
  }''',
        "recoverRun normalization",
    )

    source = replace_once(
        source,
        '''  async function continueRun(initial: Result, scope: Scope, token: number, startedAt = Date.now()): Promise<void> {
    let current = initial;''',
        '''  async function continueRun(initial: Result, scope: Scope, token: number, startedAt = Date.now()): Promise<void> {
    let current = preserveRunIdentity(initial, {
      runId: String(initial.run_id || initial.record?.identity?.run_id || ""),
      repository: initial.repository,
      customerId: initial.customer_id || scope.customerId,
      projectId: initial.project_id || scope.projectId,
      commitSha: initial.commit_sha || initial.repository_snapshot?.commit_sha,
      evidenceLedgerId: initial.evidence_ledger_id,
    });''',
        "continueRun initial normalization",
    )

    source = replace_once(
        source,
        '''        current = await requestWithRetry(
          `/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue`,
          {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({max_stages: 1}),
          },
          copy,
        );
      } catch (requestError) {
        const recovered = await recoverRun(runId);''',
        '''        const continued = await requestWithRetry(
          `/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue`,
          {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({max_stages: 1}),
          },
          copy,
        );
        current = preserveRunIdentity(continued, {
          runId,
          repository: current.repository,
          customerId: current.customer_id || scope.customerId,
          projectId: current.project_id || scope.projectId,
          commitSha: current.commit_sha || current.repository_snapshot?.commit_sha,
          evidenceLedgerId: current.evidence_ledger_id,
        });
      } catch (requestError) {
        const recovered = await recoverRun(runId, {
          repository: current.repository,
          customerId: current.customer_id || scope.customerId,
          projectId: current.project_id || scope.projectId,
          commitSha: current.commit_sha || current.repository_snapshot?.commit_sha,
          evidenceLedgerId: current.evidence_ledger_id,
        });''',
        "continuation response normalization",
    )

    source = replace_once(
        source,
        '''      const recovered = await requestWithRetry(
        `/assessment/comprehensive-run/${encodeURIComponent(persisted.runId)}`,
        {method: "GET"},
        copy,
      );
      if (token !== sequence.current) return;
      persistExactRun(recovered, scope, persisted.startedAt);''',
        '''      const recoveredResponse = await requestWithRetry(
        `/assessment/comprehensive-run/${encodeURIComponent(persisted.runId)}`,
        {method: "GET"},
        copy,
      );
      const recovered = preserveRunIdentity(recoveredResponse, {
        runId: persisted.runId,
        repository: persisted.repository,
        customerId: persisted.customerId,
        projectId: persisted.projectId,
      });
      if (token !== sequence.current) return;
      persistExactRun(recovered, scope, persisted.startedAt);''',
        "resume response normalization",
    )

    HOOK.write_text(source, encoding="utf-8")


def write_test() -> None:
    TEST.write_text(
        '''from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = (ROOT / "apps/web/app/assessment/useAssessmentRun.ts").read_text(encoding="utf-8")


def test_recovery_preserves_exact_identity_from_url_or_nested_record() -> None:
    assert "function preserveRunIdentity(value: Result, fallback: RunIdentityFallback): Result" in HOOK
    assert "value.run_id || identity.run_id || fallback.runId" in HOOK
    assert "value.commit_sha" in HOOK
    assert "value.repository_snapshot?.commit_sha" in HOOK
    assert "record: {" in HOOK
    assert "identity: {" in HOOK


def test_every_recovery_path_normalizes_before_react_state() -> None:
    assert "const recovered = preserveRunIdentity(recoveredResponse" in HOOK
    assert "current = preserveRunIdentity(continued" in HOOK
    assert "return preserveRunIdentity(recovered" in HOOK
    assert "let current = preserveRunIdentity(initial" in HOOK


def test_active_reload_uses_persisted_run_id_as_authoritative_fallback() -> None:
    resume = HOOK.split("async function resumePersistedRun", 1)[1].split("async function run()", 1)[0]
    assert "runId: persisted.runId" in resume
    assert "setResult(recovered);" in resume
    assert resume.index("const recovered = preserveRunIdentity") < resume.index("setResult(recovered);")


def test_continuation_never_replaces_exact_identity_with_bounded_projection_gaps() -> None:
    continuation = HOOK.split("async function continueRun", 1)[1].split("function applyIssue", 1)[0]
    assert "runId," in continuation
    assert "repository: current.repository" in continuation
    assert "customerId: current.customer_id || scope.customerId" in continuation
    assert "projectId: current.project_id || scope.projectId" in continuation
''',
        encoding="utf-8",
    )


def main() -> int:
    patch_hook()
    write_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
