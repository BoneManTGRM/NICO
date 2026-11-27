"""Stage an immutable owned-revision input set without any runtime source fetch."""
from __future__ import annotations
import argparse
from hashlib import sha256
import gzip
import json
from pathlib import Path
import re

BASELINE_SHA = "aec46d5ca31e19f6d7e62b65d98f8e116396782f0e164a1a7d289e5f484878f4"
TARGET = "5eb768b5776f88bae86e972c76267915cc874c85"
OVERLAYS = frozenset({
    "apps/web/app/assessment/AssessmentWorkspace.tsx",
    "apps/web/app/assessment/assessmentCopy.ts",
    "apps/web/app/assessment/assessmentEvidence.ts",
    "apps/web/vercel.json",
})
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024


def stage(candidate: Path, overlay: Path, baseline: Path, destination: Path) -> int:
    with gzip.open(baseline, "rb") as f:
        raw = f.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024 or sha256(raw).hexdigest() != BASELINE_SHA:
        raise ValueError("reference inventory digest mismatch")
    receipt = json.loads(raw)
    auth_files = {p: h for p, h in receipt["source_inventory"].items() if p.startswith("apps/web/")}
    if receipt["source_sha"] != TARGET or len(auth_files) != 210 or not OVERLAYS <= auth_files.keys():
        raise ValueError("reference inventory identity mismatch")
    candidate, overlay = candidate.resolve(strict=True), overlay.resolve(strict=True)
    material, total = {}, 0
    for name, digest in sorted(auth_files.items()):
        if not re.fullmatch(r"apps/web/[A-Za-z0-9_./()\[\]-]+", name) or any(
            segment in {"", ".", ".."} for segment in name.split("/")
        ):
            raise ValueError("reference filename invalid")
        root = overlay if name in OVERLAYS else candidate
        file = root / name
        if not file.is_file() or file.resolve(strict=True) != file:
            raise ValueError(f"reference path unavailable: {name}")
        with file.open("rb") as f:
            contents = f.read(MAX_FILE + 1)
        total += len(contents)
        if len(contents) > MAX_FILE or total > MAX_TOTAL or sha256(contents).hexdigest() != digest:
            raise ValueError(f"reference bytes mismatch: {name}")
        material[name] = contents
    # Do not leave a partial output that a later build might mistake for valid input.
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name, contents in material.items():
        file = destination / name
        file.parent.mkdir(parents=True, exist_ok=True)
        with file.open("xb") as f:
            f.write(contents)
    return len(material)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("overlay", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps({"reference_files": stage(args.candidate, args.overlay, args.baseline, args.destination),
                      "target_commit": TARGET, "compiler_observed": False}))
