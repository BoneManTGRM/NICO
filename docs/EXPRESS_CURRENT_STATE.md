# NICO Express Assessment — Current State Snapshot

**Date:** 2026-07-04
**Commit SHA:** (latest)

## What Works Now
Express currently includes:
- repo intake
- local-path Express scan through nico.cli.run_scan
- dependency audit
- CI/CD static audit
- architecture / technical-debt static audit
- maturity semaphore
- resourcing recommendation
- 30/60/90 roadmap
- Markdown / HTML / JSON / evidence manifest report writing
- CLI access through: `python -m nico assessment <target> --tier express --output <dir>`

## Current Output Files
- assessment_latest.json
- assessment_<assessment_id>.json
- assessment_latest.md
- assessment_latest.html
- evidence_manifest.json

## What Is Still Heuristic / Limited
- dependency audit is static-only unless real audit tools are added later
- CI/CD audit detects config files only, not workflow history
- architecture audit uses file-size and TODO/FIXME/XXX heuristics only
- maturity score is heuristic
- resourcing is heuristic
- roadmap is heuristic
- HTML report is still basic
- evidence manifest is basic

## What Is Not Implemented Yet
- Mid tier is not implemented
- Full tier is not implemented
- stakeholder interviews are not implemented
- QA/parity review is not implemented
- GitHub activity analysis is not implemented
- real PR/commit velocity analysis is not implemented
- real CI pass/fail history is not implemented
- real dependency vulnerability DB checks are not implemented
- no architecture diagrams/runtime profiling
- no human design review automation

## Phase 3 Recommended Focus
1. Evidence weighting across scanner/dependency/CI/architecture/maturity signals
2. Better report synthesis and recommendation ranking
3. GitHub activity module using authenticated API when token exists
4. CI/CD history module using workflow runs when available
5. Better dependency audit with pip-audit/npm audit optional execution
6. Stronger evidence manifest linking each recommendation to source signals
7. Tests preventing regression of current Express output shape

## Non-Regression Checklist
python -m py_compile nico/assessment.py nico/modules/reporting.py nico/modules/roadmap.py nico/modules/maturity.py
python -m nico assessment ./nico/test_lab --tier express --output /tmp/nico_express_snapshot
python -m pytest tests/test_phase1_regression.py tests/test_phase2_assessment_reporting.py tests/test_phase2_maturity.py tests/test_phase2_roadmap.py