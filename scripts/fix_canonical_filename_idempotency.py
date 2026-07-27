#!/usr/bin/env python3
from pathlib import Path

path = Path("nico/comprehensive_canonical_report_truth_v1.py")
source = path.read_text(encoding="utf-8")
old = '''def _normalize_filename(value: Any) -> str:
    filename = str(value or "nico-comprehensive-assessment-FINAL-PENDING-APPROVAL.pdf")
    filename = _FINAL_SUFFIX_RE.sub("-FINAL-PENDING-APPROVAL.pdf", filename)
    filename = _DRAFT_SUFFIX_RE.sub("-FINAL-PENDING-APPROVAL.pdf", filename)
    return filename
'''
new = '''def _normalize_filename(value: Any) -> str:
    filename = str(value or "nico-comprehensive-assessment-FINAL-PENDING-APPROVAL.pdf")
    if _FINAL_SUFFIX_RE.search(filename):
        return _FINAL_SUFFIX_RE.sub("-FINAL-PENDING-APPROVAL.pdf", filename)
    if re.search(r"-DRAFT\\.pdf$", filename, re.IGNORECASE):
        return re.sub(r"-DRAFT\\.pdf$", "-FINAL-PENDING-APPROVAL.pdf", filename, flags=re.IGNORECASE)
    if filename.casefold().endswith(".pdf"):
        return filename[:-4] + "-FINAL-PENDING-APPROVAL.pdf"
    return filename + "-FINAL-PENDING-APPROVAL.pdf"
'''
if source.count(old) != 1:
    raise SystemExit("canonical filename function did not match exactly")
path.write_text(source.replace(old, new, 1), encoding="utf-8")
