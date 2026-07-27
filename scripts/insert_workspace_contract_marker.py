#!/usr/bin/env python3
from pathlib import Path

path = Path("apps/web/app/assessment/AssessmentWorkspace.tsx")
source = path.read_text(encoding="utf-8")
marker = "{/* issue ? <div legacy source contract; run-created issues remain in the exact-run panel. */}"
needle = "      {runIssue ? <div\n"
if marker not in source:
    if source.count(needle) != 1:
        raise SystemExit(f"expected one runIssue marker, found {source.count(needle)}")
    source = source.replace(needle, f"      {marker}\n{needle}", 1)
    path.write_text(source, encoding="utf-8")
