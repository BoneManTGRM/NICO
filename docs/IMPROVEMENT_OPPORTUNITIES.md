# Improvement Opportunities

| Issue or opportunity | Affected area | Severity | Business impact | Technical impact | Recommended fix | Required now? | Blocks MVP? |
|---|---|---:|---|---|---|---|---|
| Run exact remote-branch validation on a developer machine | validation | medium | Reduces merge risk | Container could not clone from GitHub, so validation used a local equivalent checkout | Check out `upgrade/repair-first-foundation` directly and rerun backend/frontend/API checks | Before merge | Yes for final merge confidence |
| Add explicit raw-secret regression tests for reports/API output | tests/security | high | Prevents trust-damaging secret leakage | Current tests cover masking but should expand across report files and API responses | Add no-raw-secret assertions for report content, API JSON, and frontend state | Before ready-for-review | No |
| Complete deeper module split | backend | medium | Improves maintainability and testability | Current pass adds module foundations while keeping CLI orchestration compatible | Move remaining orchestration logic into dedicated scanner/reparodynamics/report modules | Later | No |
| Add real external scanner execution | scanners | medium | Improves credibility against standalone tools | Current pass detects tool availability and uses safe built-in fallback | Add controlled subprocess adapters with timeouts and normalized output | Later | No |
| Add Cyber Twin graph | reparodynamics/storage/UI | high | Differentiates NICO from flat scanners | No graph-backed blast-radius model yet | Implement SQLite nodes/edges and asset extraction | Later | No |
| Add AI-agent security module | scanners/UI/reports | high | Strong market wedge for AI-built apps | Current pass has normalized category and future roadmap | Add agent config fixtures and scanner | Later | No |
| Add NICO-Bench Local | tests/reports | medium | Enables proof against disconnected tools | No benchmark command in this pass | Build benchmark fixtures and optional external comparison | Later | No |
| Add production auth and RBAC | API/UI | critical | Required before hosted SaaS | Local API has no production identity layer | Add auth, RBAC, tenant isolation, and encrypted secrets | Before SaaS | No for local MVP |

Validation cleanup applied in this pass:

- TypeScript target was modernized from `es5` to `es2017`.
- Frontend config was kept compatible with the Next automatic JSX runtime.
- PR #1 should remain a draft until the exact remote branch is checked out and validated outside this container.

Next hardening priority:

- Add explicit tests proving raw fake secret values do not appear in generated reports, API JSON responses, or frontend-displayed fields.
