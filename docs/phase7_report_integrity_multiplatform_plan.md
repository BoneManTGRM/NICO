# Phase 7: Report Integrity, Decision Quality, and Multi-Platform Support

## Status

Draft implementation branch. Do not merge until every acceptance gate below is proven by exact-revision artifacts and the complete CI matrix.

## Workstreams

1. Immutable final assessment truth model used by every renderer and exporter.
2. Canonical finding identity and duplicate elimination.
3. Structured, deduplicated acceptance criteria, roadmap mappings, and backlog mappings.
4. Scanner preflight, execution classification, bounded retries, and degraded-mode truth.
5. Single scoring service and canonical limitation ledger.
6. Contextual priority calibration and component-specific decision titles.
7. Typed evidence locations for source, workflow, dependency, infrastructure, repository, artifact, and operational observations.
8. Enum-based idempotent report filenames.
9. Short client report plus separate technical appendix and raw evidence package.
10. Provider-neutral repository and CI/CD abstractions.
11. Tier 1 adapters: GitHub, GitLab, Bitbucket Cloud, Azure DevOps.
12. Tier 2 adapters: Bitbucket Data Center, Gitea, Forgejo.
13. Extension contracts for Jenkins, CircleCI, Buildkite, TeamCity, AWS CodeCommit/CodeBuild/CodePipeline, Gerrit, Perforce, and Subversion.
14. Provider capability detection, credential isolation, and immutable provider-neutral revision identity.
15. Provider conformance tests and cross-format report truth tests.

## Merge gates

- One technical score and one evidence-adjusted score across PDF, Markdown, HTML, JSON, CSV, executive brief, and appendix.
- One canonical limitation ledger and count.
- Zero duplicate canonical findings.
- Zero duplicate acceptance criteria or mappings.
- All applicable required scanners complete, or an explicitly labeled degraded assessment blocks client delivery.
- No `location-not-retained` values.
- Contextual priorities with unique decision titles.
- Exactly one valid terminal filename status.
- Provider-neutral immutable revision identity on every evidence record.
- GitHub, GitLab, Bitbucket Cloud, and Azure DevOps pass the same adapter contract tests.
- Gitea and Forgejo pass documented capability tests.
- No provider-specific terminology leaks into reports for another provider.
- English and Spanish factual parity.
- Docker, frontend, security, scanner, provider, report, and full test matrices green.
- Newly generated exact-revision report packages visibly inspected before merge.

## Delivery policy

All work remains in draft pull requests. No pull request is merged without explicit user authorization.
