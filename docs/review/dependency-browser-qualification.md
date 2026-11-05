# Dependency reviewer browser qualification

This test-only follow-up extends the reviewed local integration at `7a383d34` without changing application behavior. The original integration branch remains preserved.

The existing isolated WebKit harness now runs 20 pages: five scenarios × English/es-MX × 1280×1000 desktop/390×844 mobile. The dependency page contains 13 expanded candidate rows: qualified receipt, stale fingerprint, duplicate packet, missing packet, foreign candidate, wrong canonical index, unknown guidance, collected guidance without receipt, and all five authored missing-data guidance codes. Long package names, nested paths and full SHA-256 fingerprints exercise wrapping. Canonical indices/fingerprints deliberately differ from queue indices/fingerprints.

Assertions require qualified identity only on its bound row, correct localized guidance, suppression of untrusted/unsupported guidance, retained installation/affectedness/runtime-use caveats, and no lexical proof on dependency rows. Existing production CSS, containment, text overlap, JS-error, network, human-gate and screenshot/manifest checks still apply. Dependency list items additionally receive containment checks. No timeout, artifact cap, request restriction or browser launch setting is relaxed.

## Locally verified

- 85 Python proof/diagnostic tests passed with no offline guard events. This includes fixture identity boundaries and negative rendered-text oracle tests.
- 76 JavaScript tests passed: 74 existing reviewer-assistance cases plus two bilingual tests rendering each of the exact browser fixture's13 rows through the actual component. The rendered HTML is checked by the same text oracle used in WebKit. These checks are content/association checks, not browser geometry.
- Independent reviewer found no blocking defect; separately passed30 proof-contract tests and both new JS tests. No application or gate changes.

## Remaining supported execution

Use the existing PR job `Validate iOS stability contract` in `.github/workflows/ios-webkit-paint-proof.yml` on the final reviewed SHA. It installs the pinned normal WebKit runtime, builds the actual frontend via `python scripts/reviewer_proof_environment.py`, and executes the proof. Do not use production URLs or change sandbox settings. With that job's dependencies and real frontend build available, the exact proof command from the repository root is:

```bash
python scripts/reviewer_binding_webkit_proof.py \
  --expected-sha "$(git rev-parse HEAD)" \
  --reviewed-head "$(git rev-parse HEAD)" \
  --output reviewer-binding-webkit-proof
```

For a GitHub PR merge checkout, use the actual reviewed PR head for `--reviewed-head`; the script requires it to equal the checkout or a direct merge parent. The output directory must be new. Existing workflow diagnostics/artifact steps finalize and retain bounded proof output; do not manually label partial output successful.

Required evidence: a complete20-case manifest bound to checkout/tree/reviewed-head; 20 screenshot hashes and images; loaded production CSS records; bounded GET-only loopback request records; no JS errors, overflow or overlapping text; identity/guidance assertions passing for both languages and widths. Inspect actual dependency screenshots in addition to automated results. Existing180-second proof budget, four-minute workflow step and20MiB aggregate artifact ceiling remain unchanged; if the larger fixture exceeds them, qualification fails and requires investigation, not silent relaxation.

Browser execution remains pending. The earlier normal Chromium probe failed before page creation because its sandbox helper was misconfigured, and no production Next build is present locally. No browser launch was retried, no runtime installed, no sandbox bypass used, and no pixel qualification claimed. No PR or workflow publication/dispatch performed.
