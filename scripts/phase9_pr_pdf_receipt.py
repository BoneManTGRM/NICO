"""Write only measured, synthetic fixture metadata for successful PR checks."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys

from pypdf import PdfReader

GROUPS = {
    "spanish": ("phase9-synthetic-spanish-proof", ["nico-es-MX-synthetic-draft.pdf"]),
    "parity": ("owned-parity-pdf-proof", [f"{s}-{l}.pdf" for s in ("small", "rich", "phase9") for l in ("en", "es-MX")]),
    "seven-row": ("owned-seven-row-pdf-proof", ["en.pdf", "es-MX.pdf"]),
}


def emit(group, revision):
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError
    folder, names = GROUPS[group]
    rows = []
    for name in names:
        p = Path(folder) / name
        if p.parent.is_symlink() or p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size <= 100_000_000:
            raise ValueError
        data = p.read_bytes()
        pages = len(PdfReader(io.BytesIO(data), strict=True).pages)
        if not data.startswith(b"%PDF-") or not 0 < pages <= 5000:
            raise ValueError
        rows.append(dict(fixture=name, sha256=hashlib.sha256(data).hexdigest(), pages=pages, bytes=len(data)))
    target = Path(os.environ["RUNNER_TEMP"]) / ("phase9-pr-receipt-" + group)
    target.mkdir(mode=0o700, exist_ok=False)
    with (target / "check.json").open("x") as f:
        json.dump(dict(schema="nico.synthetic-pr-pdf.v1", revision=revision, fixtures=rows), f, separators=(",", ":"))


if __name__ == "__main__":
    emit(sys.argv[1], os.environ["PHASE9_REVISION"])
