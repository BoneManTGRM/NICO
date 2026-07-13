# Contributing to NICO

NICO accepts defensive, authorized, evidence-bound improvements. Contributions must preserve the safety boundary, truthfulness rules, exact-run identities, and required human review.

## Before opening a change

- Read `ARCHITECTURE.md`, `docs/OPERATOR_GUIDE.md`, `docs/PROJECT_STATUS.md`, and `SECURITY.md`.
- Search existing issues and pull requests.
- Keep the change narrowly scoped.
- Use synthetic or explicitly authorized fixtures only.
- Never commit credentials, private repository data, delivery tokens, client reports, or raw secret findings.

## Development setup

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pytest

cd apps/web
npm install
npm run lint
npm run build
```

See the README and `docs/NO_SERVER_ASSESSMENT.md` for local operation.

## Pull-request requirements

A pull request should include:

1. the problem and evidence;
2. the smallest safe change;
3. tests or a reason tests are not applicable;
4. safety and authorization impact;
5. truthfulness impact;
6. migration or rollback notes when state, routes, reports, or persistence change; and
7. exact commands used for verification.

Do not merge a pull request with failed required checks, unresolved review threads, unexplained score changes, or deployment claims unsupported by exact-SHA evidence.

## Coding rules

- Prefer explicit state over inferred success.
- Treat missing evidence as unavailable, not passed.
- Keep `shell=False` for subprocess execution.
- Bound runtime, repository size, and retained output.
- Redact secrets before persistence, logs, reports, or UI display.
- Preserve customer, project, run, scan, report, approval, and artifact identities.
- Make retries idempotent where duplicate artifacts would be harmful.
- Keep approval and client delivery as explicit human-controlled actions.
- Do not introduce offensive capability or bypass authorization gates.

## Tests

Add the smallest regression test that would fail before the change. For workflow changes, cover both the successful path and at least one unavailable, blocked, mismatched, or failed path.

Tests must not convert placeholders into passing evidence. Synthetic fixtures must be clearly marked and isolated from live output.

## Documentation

Update canonical documents instead of adding another versioned or patch-specific guide. Historical implementation notes may be added when they are clearly labeled and linked from the relevant issue or pull request.

## Security reports

Do not open a public issue for a suspected vulnerability that could expose users or credentials. Follow `SECURITY.md`.

## Licensing

By contributing, you confirm that you have the right to submit the work and that it may be distributed under NICO's repository licensing terms. A contribution does not grant commercial-use rights beyond those terms.
