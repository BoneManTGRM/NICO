# NICO No-Server Authorized Assessment Mode

NICO can test your own systems and systems you are explicitly authorized to assess without a public backend, hosted server, Render, Railway, Fly.io, or paid infrastructure.

This mode runs from the local CLI and keeps `app.nicoaudit.com` optional until a hosted dashboard is worth deploying.

## Safety boundary

No-server assessment is defensive-only and authorized-access-only.

Allowed:

- Local repository/folder assessment
- Read-only GitHub repository assessment
- Uploaded `.zip` / `.tar` project archive assessment
- Passive-only checks for a local/staging URL you own or are authorized to assess

Blocked:

- Unauthorized scanning
- Exploitation
- Brute force
- Authentication bypass
- Credential theft
- Phishing
- Malware
- Stealth/evasion
- Persistence
- Destructive actions
- Crawling or scanning unrelated hosts

Every non-demo assessment requires explicit confirmation with `--authorized`.

## Commands

### Local repository/folder

```bash
python -m nico assess local /path/to/project --authorized
```

### GitHub repository

```bash
python -m nico assess github owner/repo --authorized
```

or:

```bash
python -m nico assess github https://github.com/owner/repo --authorized
```

For private repositories, set a local read-only token before running:

```bash
export NICO_GITHUB_TOKEN=your_read_only_token
```

The token stays local. It is not exposed to the frontend.

### Project archive

```bash
python -m nico assess archive ./project.zip --authorized
```

Supported archive formats: `.zip`, `.tar`, `.tar.gz` and other tar-compatible formats.

NICO extracts the archive into a safe temporary directory and blocks path traversal attempts.

### Authorized passive URL

```bash
python -m nico assess url https://staging.example.com --passive-only --authorized
```

URL mode is passive only. It checks only the explicitly provided URL for reachability, redirects, visible response headers, visible cookie flags, visible CORS headers, and basic TLS certificate metadata when available.

It does not crawl, fuzz, exploit, brute force, bypass auth, or send destructive traffic.

### Latest assessment

```bash
python -m nico assess latest
```

### Reports

```bash
python -m nico assess report latest --format markdown
python -m nico assess report latest --format html
python -m nico assess report latest --format json
```

Reports are written under `.nico/reports/`:

```text
no_server_latest.json
no_server_latest.md
no_server_latest.html
```

### Verification

```bash
python -m nico assess verify latest
```

## Assessment modules

NICO no-server mode produces an Express Technical Health Assessment with these sections:

- Executive Summary
- Authorization Scope
- Target Summary
- Maturity Semaphore: Red / Yellow / Green
- Code Audit
- Dependency / Library Ecosystem
- Secrets Exposure Review
- CI/CD Analysis
- Architecture & Technical Debt
- Passive URL Review if used
- Bug-Risk Findings
- Repair Recommendations
- Verification Checklist
- Quick Wins
- Medium-Term Plan
- Resourcing Recommendation
- Risk Register
- Evidence Log
- Unavailable Data Notes

## Truth rules

- No fake results.
- No placeholder findings.
- No invented vulnerabilities.
- Raw secrets are masked and fingerprinted; full secret values are not printed.
- Every score is based on scanned files, visible passive URL evidence, command results, or explicit unavailable-data notes.
- If a local tool is missing, NICO reports that the tool is unavailable and continues with available checks.
- If data cannot be checked safely, NICO marks it unavailable.

## Recommended first test

Run the built-in test lab first:

```bash
python -m nico scan-test-lab
python -m nico assess local nico/test_lab --authorized
python -m nico assess report latest --format markdown
python -m nico assess verify latest
```

Then run the same flow against your own authorized project.
