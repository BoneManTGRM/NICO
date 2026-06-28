# Improvement Opportunities

| Issue or opportunity | Affected area | Severity | Business impact | Technical impact | Recommended fix | Required now? | Blocks MVP? |
|---|---|---:|---|---|---|---|---|
| Complete deeper module split | backend | medium | Improves maintainability and testability | Current pass adds module foundations while keeping CLI orchestration compatible | Move remaining orchestration logic into dedicated scanner/reparodynamics/report modules | Later | No |
| Add real external scanner execution | scanners | medium | Improves credibility against standalone tools | Current pass detects tool availability and uses safe built-in fallback | Add controlled subprocess adapters with timeouts and normalized output | Later | No |
| Add Cyber Twin graph | reparodynamics/storage/UI | high | Differentiates NICO from flat scanners | No graph-backed blast-radius model yet | Implement SQLite nodes/edges and asset extraction | Later | No |
| Add AI-agent security module | scanners/UI/reports | high | Strong market wedge for AI-built apps | Current pass has normalized category and future roadmap | Add agent config fixtures and scanner | Later | No |
| Add NICO-Bench Local | tests/reports | medium | Enables proof against disconnected tools | No benchmark command in this pass | Build benchmark fixtures and optional external comparison | Later | No |
| Add production auth and RBAC | API/UI | critical | Required before hosted SaaS | Local API has no production identity layer | Add auth, RBAC, tenant isolation, and encrypted secrets | Before SaaS | No for local MVP |
