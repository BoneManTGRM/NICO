# Supported Scanner Contract

NICO combines built-in evidence checks with controlled external scanners. A scanner is never treated as passed merely because it was requested. Every requested tool must be recorded as complete, unavailable, failed, or timed out.

## Hosted scanner matrix

| Tool | Purpose | Default version contract | Installation path |
|---|---|---:|---|
| `pip-audit` | Python dependency vulnerability evidence | `2.10.1` | Python dependency |
| `bandit` | Python static-security evidence | `1.9.4` | Python dependency |
| `semgrep` | Multi-language static-analysis evidence | `1.169.0` | Python dependency |
| `osv-scanner` | Lockfile and dependency vulnerability evidence | `v2.4.0` | Pinned GitHub release asset |
| `gitleaks` | Secret-pattern repository evidence | `v8.30.1` | Pinned GitHub release asset |
| `trufflehog` | Secret-verification and history evidence | `v3.95.9` | Pinned GitHub release asset |
| `eslint` | JavaScript/TypeScript quality evidence | Image-resolved npm package | Global npm installation |
| `tsc` | TypeScript compile evidence | Image-resolved npm package | Global npm installation |

The Python versions above are pinned in `requirements.txt`. Binary release tags are pinned in `scripts/install_hosted_scanner_binaries.py`.

## Binary version overrides

The pinned defaults may be overridden deliberately at image-build time:

```bash
NICO_OSV_SCANNER_VERSION=v2.4.0
NICO_GITLEAKS_VERSION=v8.30.1
NICO_TRUFFLEHOG_VERSION=v3.95.9
```

Overrides must be valid release tags. The installer requests the exact GitHub release tag, verifies the returned tag, restricts downloads to allowlisted GitHub hosts, bounds download size, and blocks unsafe archive paths, symlinks, and non-regular archive members.

Do not use unreviewed `latest` resolution in a production image. Version changes should be made through a pull request with:

1. the intended release tag;
2. upstream release-note review;
3. strict installer execution in CI;
4. Docker build proof;
5. scanner parsing and report-truth regression tests;
6. an authorized deployed smoke assessment before claiming production behavior.

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
