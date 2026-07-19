# Express self-repair evidence — 2026-07-19

Production Express generated a 65-page report for `BoneManTGRM/NICO` at snapshot `da8ac4e1937b`. The report reached a source maturity score of 82/100 and an evidence-adjusted score of 61/100 while retaining required human review and blocked client delivery.

The report also exposed a deterministic false-positive family: the Python-only `python_eval_exec` rule was attached to TypeScript/TSX files where the source operation is JavaScript `RegExp.exec`. Those findings appeared in both Code Audit and Static Analysis and were duplicated into the finding dossier.

The repair in this branch adds language-aware classification so Python eval/exec evidence remains reviewable in Python files while JavaScript/TypeScript rule mismatches are retained as review metadata and excluded from production-risk scoring.

This document is evidence provenance only. Fresh deployed Express, Mid, and Full proof remains required before issue #529 can close.
