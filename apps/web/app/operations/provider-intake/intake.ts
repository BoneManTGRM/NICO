export type IntakeInput = {
  repository: string; expected_commit_sha: string; customer_id: string; project_id: string;
  authorized_by: string; authorization_scope: string; authorization_confirmed: boolean;
  report_language: 'en' | 'es-MX'; execution_mode: 'internal_test' | 'controlled_pilot' | 'production_engagement';
};
export type Attempt = {
  requestId: string; submittedAt: string; repository: string; commitSha: string;
  state: 'pending' | 'uncertain' | 'received'; runId?: string; receivedAt?: string;
};
export const ATTEMPT_KEY = 'nico.operator-provider-intake.attempt.v1';
type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
const SHA = /^[a-f0-9]{40}$/i;
const REPO = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const RUN = /^comprun_[a-f0-9]{32}$/;

export function payloadFor(input: IntakeInput) {
  const repository = input.repository.trim();
  const commit = input.expected_commit_sha.trim().toLowerCase();
  // The existing backend normalizer removes literal .git substrings. Reject them
  // here before acquisition so explicit authorization cannot change repository.
  if (repository.includes('.git') || !REPO.test(repository) || repository.split('/').some(part => part === '.' || part === '..') || !SHA.test(commit)) throw new Error('invalid_source');
  if (!input.authorization_confirmed || !input.authorized_by.trim() || !input.authorization_scope.trim() ||
      !input.customer_id.trim() || !input.project_id.trim()) throw new Error('authorization_required');
  if (!['en', 'es-MX'].includes(input.report_language) || !['internal_test', 'controlled_pilot', 'production_engagement'].includes(input.execution_mode)) throw new Error('invalid_mode');
  // Explicit allowlist: credentials and arbitrary provider controls cannot enter the JSON body.
  return {provider: 'github', repository, expected_commit_sha: commit,
    customer_id: input.customer_id.trim(), project_id: input.project_id.trim(),
    authorized_by: input.authorized_by.trim(), authorization_scope: input.authorization_scope.trim(),
    authorized: true, authorization_confirmed: true, assessment_depth: 'strategic',
    report_language: input.report_language, execution_mode: input.execution_mode};
}

export function readAttempt(store: Store): Attempt | null {
  const raw = store.getItem(ATTEMPT_KEY);
  if (!raw) return null;
  const data = JSON.parse(raw);
  if (!data || !['pending', 'uncertain', 'received'].includes(data.state) ||
      typeof data.requestId !== 'string' || !/^[a-f0-9-]{36}$/.test(data.requestId) ||
      typeof data.submittedAt !== 'string' || !Number.isFinite(Date.parse(data.submittedAt)) ||
      typeof data.repository !== 'string' || !REPO.test(data.repository) || !SHA.test(data.commitSha) ||
      (data.runId !== undefined && !RUN.test(data.runId))) throw new Error('attempt_record_unreadable');
  return {requestId: data.requestId, submittedAt: data.submittedAt, repository: data.repository,
    commitSha: data.commitSha, state: data.state, ...(data.runId ? {runId: data.runId} : {}),
    ...(typeof data.receivedAt === 'string' ? {receivedAt: data.receivedAt} : {})};
}

export async function submitIntake(input: IntakeInput, token: string, store: Store, send: typeof fetch = fetch): Promise<Attempt> {
  const payload = payloadFor(input);
  if (!token.trim()) throw new Error('admin_required');
  if (store.getItem(ATTEMPT_KEY)) throw new Error('existing_attempt');
  const attempt: Attempt = {requestId: crypto.randomUUID(), submittedAt: new Date().toISOString(),
    repository: payload.repository, commitSha: payload.expected_commit_sha, state: 'pending'};
  // Save before the POST. If saving fails, no remote work is requested.
  store.setItem(ATTEMPT_KEY, JSON.stringify(attempt));
  try {
    const response = await send('/api/nico/providers/operator/comprehensive-intake', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-NICO-Admin-Token': token.trim(), 'X-Request-ID': attempt.requestId},
      body: JSON.stringify(payload), cache: 'no-store', redirect: 'error',
    });
    const data = await response.json();
    // This specific rejection happens before any provider or assessment action.
    if (response.status === 403 && data?.detail?.code === 'authorized_nico_operator_required') {
      store.removeItem(ATTEMPT_KEY);
      throw new Error('admin_required');
    }
    // A valid returned ID remains a recovery reference even if other receipt fields conflict.
    if (typeof data?.run_id === 'string' && RUN.test(data.run_id)) {
      attempt.runId = data.run_id;
      attempt.receivedAt = new Date().toISOString();
    }
    const snapshot = data?.repository_snapshot;
    if (!response.ok || data?.operation !== 'operator_provider_intake_started' ||
        !RUN.test(data?.run_id) || snapshot?.run_id !== data.run_id ||
        snapshot?.repository !== attempt.repository || snapshot?.commit_sha !== attempt.commitSha ||
        snapshot?.status !== 'attached' || snapshot?.exact_commit_verified !== true) throw new Error('unverified_receipt');
    const received: Attempt = {...attempt, state: 'received', runId: data.run_id, receivedAt: new Date().toISOString()};
    store.setItem(ATTEMPT_KEY, JSON.stringify(received));
    return received;
  } catch (error) {
    if (error instanceof Error && error.message === 'admin_required') throw error;
    const uncertain: Attempt = {...attempt, state: 'uncertain'};
    try { store.setItem(ATTEMPT_KEY, JSON.stringify(uncertain)); } catch { /* Original pending record still prevents resubmission. */ }
    return uncertain;
  }
}
