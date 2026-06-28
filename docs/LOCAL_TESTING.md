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
- Frontend `npm run build` passed.
- Frontend `npm run dev` started successfully.

Known limitation:

- The exact remote branch should still be checked out and run on a developer machine or Codex environment before merging because this environment cannot clone from GitHub.
- Keep PR #1 as draft until exact-branch validation is complete.
