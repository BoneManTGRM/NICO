from __future__ import annotations

import json
from pathlib import Path

from nico.full_assessment_complexity_evidence import collect_complexity_evidence

ROOTS = (Path("nico"), Path("apps/web"), Path("scripts"))
SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
SKIP_PARTS = {"node_modules", ".next", "dist", "build", "coverage", "__pycache__", ".git"}
MAX_FILE_BYTES = 1_000_000


def collect_files() -> dict[str, str]:
    files: dict[str, str] = {}
    for root in ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink() or path.suffix.lower() not in SUFFIXES:
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            files[path.as_posix()] = path.read_text(encoding="utf-8", errors="replace")
    return files


def markdown(evidence: dict) -> str:
    lines = [
        "# NICO Complexity Remediation Manifest",
        "",
        f"- Files analyzed: {evidence.get('files_analyzed', 0)}",
        f"- Functions measured: {evidence.get('functions_measured', 0)}",
        f"- Average complexity: {evidence.get('average_cyclomatic_complexity')}",
        f"- Maximum complexity: {evidence.get('maximum_cyclomatic_complexity')}",
        f"- High-complexity functions: {evidence.get('high_complexity_functions', 0)}",
        f"- Very-high-complexity functions: {evidence.get('very_high_complexity_functions', 0)}",
        f"- Long functions: {evidence.get('long_functions', 0)}",
        f"- Deeply nested functions: {evidence.get('deep_nesting_functions', 0)}",
        f"- Duplicate block groups: {(evidence.get('duplicate_evidence') or {}).get('duplicate_block_groups', 0)}",
        "",
        "## Highest-priority hotspots",
        "",
    ]
    hotspots = evidence.get("hotspots") if isinstance(evidence.get("hotspots"), list) else []
    if not hotspots:
        lines.append("None recorded.")
    for item in hotspots:
        lines.append(
            f"- `{item.get('path')}:{item.get('line')}` `{item.get('name')}` — complexity={item.get('cyclomatic_complexity')}, "
            f"loc={item.get('loc')}, nesting={item.get('max_nesting')}, hotspot={item.get('hotspot_score')}"
        )
    lines.extend(["", "## Duplicate samples", ""])
    duplicate = evidence.get("duplicate_evidence") if isinstance(evidence.get("duplicate_evidence"), dict) else {}
    samples = duplicate.get("samples") if isinstance(duplicate.get("samples"), list) else []
    if not samples:
        lines.append("None recorded.")
    for sample in samples:
        locations = ", ".join(
            f"{item.get('path')}:{item.get('start_line')}"
            for item in (sample.get("occurrences") or [])
            if isinstance(item, dict)
        )
        lines.append(f"- `{sample.get('fingerprint')}` — {locations}")
    lines.extend(
        [
            "",
            "This artifact contains metrics and locations only. Refactoring requires regression tests and human review; it does not authorize automatic behavior changes.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    output = Path("remediation-evidence/complexity-manifest.json")
    evidence = collect_complexity_evidence(collect_files())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output.with_suffix(".md").write_text(markdown(evidence), encoding="utf-8")
    print(
        json.dumps(
            {
                "files_analyzed": evidence.get("files_analyzed"),
                "functions_measured": evidence.get("functions_measured"),
                "high_complexity_functions": evidence.get("high_complexity_functions"),
                "very_high_complexity_functions": evidence.get("very_high_complexity_functions"),
                "maximum_cyclomatic_complexity": evidence.get("maximum_cyclomatic_complexity"),
                "duplicate_block_groups": (evidence.get("duplicate_evidence") or {}).get("duplicate_block_groups"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
