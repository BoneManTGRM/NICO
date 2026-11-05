# Bounded Spanish render diagnostic

Source base: `bb8e4ae645114d25a7b43f7165764c35c3db6186`.
Live refs checked before completion: ordinary draft branch unchanged at that
commit; main `568d5c530b9a7ecdd892d8b7f5023ba5d348e0d9`.

This is synthetic diagnostic infrastructure, not a production performance fix.
The retained attachment was not physically received in this executor. The
documented Library transfer helper returned `download failed`, its generic
`urllib.error.URLError` path. It did not expose the underlying transport reason
and created no ZIP. This establishes neither an HTTP denial nor an expired
reference. No alternate transfer route was attempted. Actual ZIP, manifest,
canonical digest and run/revision/target verification remain outstanding here.
No private inputs are included in this change.

Run with the repository test dependencies installed:

```sh
python -m pytest -q tests/test_ordinary_spanish_profile_harness.py
python -m scripts.profile_ordinary_spanish_render --output /tmp/new-profile.json --wall-seconds 120 --cpu-seconds 100
```

The harness uses the owned fixed fixture and installed production wrappers,
without starting an assessment. It measures baseline and profiled Spanish
rendering, counts copying, recursive traversal, localization and extraction,
and records existing inclusive phase timings. Category names are heuristics;
inclusive timings overlap and must not be added. Profiling includes separately
timed verification extraction and materially increases execution time.

Validation: **5 tests passed in 2.50 seconds**. A full bounded synthetic run
also passed. Baseline rendering took 3.781 seconds wall / 3.784 CPU; profiled
rendering took 21.197 wall / 21.194 CPU. Verification extraction took 0.718 wall /
0.720 CPU. The route made 42 PDF text lookups and 12 parses; baseline inclusive
parse time was 1.053 seconds. This small fixture cannot identify the retained
report's production hotspot.

Both executions produced identical 22-page, 174592-byte PDFs:
`824dbd6880bc8759efaa29bcb1f1751113baad59b7c8b0023b21e4674a82f94d`.
Extracted text SHA-256:
`613b71dd45c160610709b53c8996455c7003c9df3353ae2e07e4228abc92a914`.
The entire synthetic input and assessment truth projection remained unchanged.
Artifact hashes, run/commit/truth binding, Spanish locale, no-rerun,
pending-human-approval, blocked delivery and delivery disallowed were asserted.
No production validation or approval gate was modified.

Independent read-only review found two issues: direct worker output overwrite
and ambiguous profile scope. Exclusive creation, a direct-worker preservation
test and explicit scope resolve both; final review found no blocking findings.
Raw synthetic profile remains outside git at
`/workspace/nico-synthetic-spanish-profile-final.json`.

Still required: supported physical receipt and manifest admission of the actual
retained ZIP, bounded actual-input profiling, a demonstrated hotspot, narrow
repair if justified, independent review and retained-input semantic/performance
acceptance. Existing draft PR CI evidence does not prove those steps.
