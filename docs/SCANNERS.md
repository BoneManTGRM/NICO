# Supported Scanner Contract

NICO combines built-in evidence checks with controlled external scanners. A scanner is never treated as passed merely because it was requested. Every requested tool must be recorded as complete, unavailable, failed, or timed out.

## Hosted scanner matrix

| Tool | Purpose | Default version contract | Installation path |
|---|---|---:|---|
| `pip-audit` | Python dependency vulnerability evidence | `2.10.1` | Python dependency |
| `bandit` | Python static-security evidence | `1.9.4` | Python dependency |
| `npm-audit` | npm lockfile vulnerability evidence | npm supplied by the worker image; record actual version | Worker npm installation |
| `semgrep` | Bounded Python/JavaScript/TypeScript pattern evidence | `1.170.0` | Isolated Python environment in Docker image |
| `osv-scanner` | Source dependency vulnerability evidence | `v2.3.8` | Pinned GitHub release asset |
| `gitleaks` | Secret-pattern repository evidence | `v8.30.1` | Pinned GitHub release asset |
| `trufflehog` | Secret-detector and history evidence; active verification disabled | `v3.95.0` | Pinned GitHub release asset |
| `eslint` | Bounded JavaScript/TypeScript quality evidence | `9.39.3` image default | Global npm installation |
| `tsc` | Project-configured TypeScript compile evidence | Project-local compiler; image default `6.0.3` | Prepared project dependencies; image also includes a global compiler |

`pip-audit` and `bandit` versions are pinned in `requirements.txt`. Semgrep and image Node-tool versions are pinned through `Dockerfile` build arguments. Binary release defaults are declared in `Dockerfile` and `scripts/install_hosted_scanner_binaries.py`. The hosted TypeScript runner uses the prepared project-local compiler and project configuration, so record its actual version rather than infer it from the global image compiler.

## Binary version overrides

The pinned defaults may be overridden deliberately at image-build time:

```bash
NICO_OSV_SCANNER_VERSION=v2.3.8
NICO_GITLEAKS_VERSION=v8.30.1
NICO_TRUFFLEHOG_VERSION=v3.95.0
```

Overrides must be valid release tags. The installer requests the exact GitHub release tag, verifies the returned tag, restricts downloads to allowlisted GitHub hosts, bounds download size, and blocks unsafe archive paths, symlinks, and non-regular archive members.

Do not use unreviewed `latest` resolution in a production image. Version changes should be made through a pull request with:

1. the intended release tag;
2. upstream release-note review;
3. strict installer execution in CI;
4. Docker build proof;
5. scanner parsing and report-truth regression tests;
6. an authorized deployed smoke assessment before claiming production behavior.

## Hosted execution scope and qualification limits

- **Dependencies:** `pip-audit` selects a `requirements.txt`; it does not establish complete coverage of every Python declaration or deployed installation. `npm-audit` checks discovered `package-lock.json` files with adjacent `package.json` using `--package-lock-only --ignore-scripts`. OSV recursively scans source dependencies; source-resolved package versions require corroboration before being described as installed or runtime-applicable versions.
- **Bandit:** the JSON runner excludes generated, dependency, test, fixture, example, sample and vendor paths using the explicit list in `nico/bandit_json_execution_v61.py`. A directory name does not prove its contents are irrelevant to the authorized scope. Review exclusion applicability before claiming coverage.
- **Semgrep:** the hosted profile is `config/nico-semgrep-standard.yml`: six rules for Python `eval`, `exec`, subprocess `shell=True`, requests `verify=False`, and JavaScript/TypeScript `eval` and `new Function`. It is distinct from the broader bundled `nico/semgrep_rules_v1.yml` and CI `--config auto`; execution of one does not establish coverage of the others. The source recipe excludes `node_modules`, `.next`, `dist` and `build` and uses bounded rule timeouts.
- **ESLint:** the canonical hosted runner uses a generated flat configuration with `--no-config-lookup`, basic correctness rules and generated/dependency exclusions. It does not execute the repository's own ESLint configuration or establish general security coverage. The configuration recipe is in `nico/scanner_evidence_pipeline_v1.py`; the canonical runner is in `nico/phase6_final_remediation_v1.py`.
- **TypeScript:** compilation follows the selected project's `tsconfig.json` and its checking/exclusion settings. A successful compile is not evidence of runtime behavior or security testing.
- **Secrets:** Gitleaks and TruffleHog retain detector evidence and history metadata. TruffleHog uses `--no-verification` and is bound to `HEAD`; no active credential-validity check is implied. The `full_history_verified` metadata checks that the local repository is non-shallow. It does not independently prove that every remote branch, tag or unreachable object was fetched and scanned. When only snapshot coverage is available, history limitations must remain explicit.

These descriptions document current behavior; they do not reduce agreed assessment or specialist-qualification requirements. A completed tool execution, retained output hash, zero findings or configuration hash is not a full-coverage PASS. Required rule breadth, effective configuration, included/excluded targets and applicability must be reconciled with the authorized scope. Unverified coverage remains unresolved until that evidence and review are complete.

The retained `command_intent` is an abbreviated, redacted preview of the first ten arguments. New canonical executions also retain a structured `scanner_execution_receipt`: ordered arguments returned by the runner (including delegated HEAD restrictions), forwarded working directory, exit/timeout state, explicit exclusion arguments and bounded pre/post hashes of observable input files. Argument capture limits are explicit; credentials and URL query values are redacted and environment values are omitted. Config discovery candidates are labeled as candidates, not proven loaded inputs. NICO-generated Semgrep and ESLint profile content is retained in bounded, safely redacted form only when the observed file hash matches bytes registered at generation; original-byte and redacted-content hashes distinguish these representations. Arbitrary repository configurations remain hash-only. npm project invocations and OSV fallback attempts retain separate receipts. Inventory and compact report records retain verified receipt digests and quality states without copying command paths or target lists.

Coverage observations derive only from hash-verified native output: Semgrep reported scanned/skipped paths and errors, Bandit metric paths and errors, and ESLint file paths and reported fatal-error counts. Missing fields remain unknown; bounded or invalid observations retain their limitation. These are tool-reported observations, not a repository target census. Receipts do not prove implicit configuration, inherited settings, rule applicability or complete coverage; those fields remain explicitly unverified. Historical runs without receipts remain unverified and cannot be repaired retrospectively from source recipes. Qualification requires reconciling the actual authorized profile and evidence-supported operating limitations with the frozen requirements; a different bundled rule profile alone does not establish a requirement to broaden scope.

## Execution outcomes

NICO records one of the following outcomes for every requested scanner:

- **complete** — the tool executed and its result was parsed;
- **unavailable** — the binary, manifest, language, or required environment was absent;
- **failed** — execution or parsing failed;
- **timed out** — the bounded tool deadline expired;
- **recovery required** — execution stopped updating and requires an explicit same-ID operator action.

Unavailable, failed, timed-out, queued, running, or recovery-required tools receive no passing credit.

## Time limits

Hosted defaults are configured through environment variables such as:

- `NICO_TOOL_TIMEOUT_SECONDS`
- `NICO_TOTAL_SCAN_TIMEOUT_SECONDS`
- `NICO_OSV_TIMEOUT_SECONDS`
- `NICO_HISTORY_TOOL_TIMEOUT_SECONDS`

Increasing a timeout can increase cost and exposure to untrusted repository content. Treat changes as deployment configuration changes requiring review and smoke proof.

## Project commands

Project-controlled commands are higher risk than fixed scanner invocations. Keep `NICO_ALLOW_PROJECT_COMMANDS=false` unless the deployment has an explicit sandbox, resource limits, authorized target, reviewed command policy, and operator approval.

## Version evidence

Assessment evidence should retain the requested tool name, execution outcome, and available version evidence. A report must disclose when the installed version could not be identified. Version presence does not imply that the scanner covered every file or vulnerability class.
