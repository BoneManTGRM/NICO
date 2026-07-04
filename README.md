# MalamuteNICO-Auditor (Fixed & Real)

**Local-only, no server. Paste URL → real clone + NICO scan + RYE scoring + reports.**

## Quick Start
```bash
python -m nico auditor https://github.com/octocat/Hello-World --tier full --swarm
```

Or for any public repo (iOS/Android welcome).

## What it actually does now
- Clones the repo locally (safe, private)
- Runs full NICO engine (secrets, appsec, deps, logs)
- Applies RYE scoring + TGRM repairs ranked by yield
- Generates owner/developer/reparodynamic/compliance reports
- Supports Express/Mid/Full + Retainer mode + --swarm

## Matches Malamute PDF Blueprint
Express Tier (minutes) → Mid Tier (hours) → Retainer (persistent)
RYE everywhere, swarm bug finding, simulated stakeholder from docs, auto ceremonies/logs.

## iPhone Ready
Use a-Shell or Pythonista → run the command above.

PR #1 foundation restored. All CLI + tests pass. Production-ready for local use.