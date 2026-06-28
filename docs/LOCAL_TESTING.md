# Local Testing

Use these commands before merging the repair-first foundation branch.

## Backend smoke checks

```bash
python -m pip install -r requirements.txt
pytest -q
python -m nico scan-test-lab
python -m nico scan-drift-demo
python -m nico scan ./nico/test_lab/sample_repo
python -m nico report latest
python -m nico report owner
python -m nico report developer
python -m nico report reparodynamic
python -m nico report compliance
python -m nico verify latest
python -m nico memory
python -m nico policy show
python -m nico scanner-availability
```

## API checks

Start the API:

```bash
python run_local.py
```

Then check:

```text
GET /health
POST /scan/test-lab
POST /scan/drift-demo
GET /scans/latest
GET /findings
GET /drift
GET /repairs
GET /verification/latest
POST /verification/latest
POST /verification/repair/{repair_id}
GET /memory
GET /reports
GET /reports/latest
POST /reports/generate
GET /reports/owner
GET /reports/developer
GET /reports/reparodynamic
GET /reports/compliance
GET /policy
GET /audit-log
GET /scanner-availability
GET /findings/{finding_id}
GET /repairs/{repair_id}
```

## Frontend checks

```bash
cd apps/web
npm install
npm run lint
npm run build
npm run dev
```

`npm run dev` is long-running and should start a local server at `http://localhost:3000`.

## Validation pass notes

The validation pass used a local equivalent checkout because the execution container could not resolve `github.com` for a direct branch clone.

Passed locally:

- `pytest -q` returned 9 passing tests.
- All backend CLI smoke commands listed above completed.
- FastAPI started through `python run_local.py`.
- API endpoints listed above returned HTTP 200 using generated finding and repair IDs.
- Frontend `npm run lint` passed after the TypeScript target was modernized.
- Frontend `npm run build` passed after the frontend config was kept compatible with Next's automatic JSX runtime.
- Frontend `npm run dev` started successfully.

CI cleanup applied:

- Added `httpx>=0.27` so FastAPI `TestClient` tests have their required runtime dependency in CI.
- Updated NICO Repair-First CI frontend setup to run from `apps/web`, use `npm install`, and avoid missing lockfile cache failures.
- Replaced the broad Node matrix workflow with a NICO-specific frontend workflow that runs only lint/build from `apps/web`.
- Updated the matching Node.js workflow on `main` so the PR no longer has an add/add workflow conflict.
- Kept CodeQL unchanged because CodeQL passed.

Known limitation:

- The exact remote branch should still be checked out and run on a developer machine or Codex environment before merging because this environment cannot clone from GitHub.
- Keep PR #1 as draft until exact-branch validation and GitHub Actions are green.
- Add explicit no-raw-secret report/API regression tests in the next hardening pass before marking ready for review.
