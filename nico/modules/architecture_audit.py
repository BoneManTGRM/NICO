"""Architecture & Technical Debt Module (Phase 2)

Basic static signals for architecture risk and technical debt.
"""

from pathlib import Path


def audit_architecture(target: str) -> dict:
    result = {
        "target": target,
        "status": "limited",
        "debt_signals": [],
        "large_files": [],
        "todo_clusters": 0,
        "limitations": []
    }

    path = Path(target)
    if not path.exists():
        result["limitations"].append("Target does not exist")
        return result

    todo_count = 0
    large_files = []

    for file_path in path.rglob("*"):
        if file_path.is_file():
            try:
                # Skip very large binary-ish files
                if file_path.stat().st_size > 500_000:
                    large_files.append(str(file_path.relative_to(path)))
                    continue

                text = file_path.read_text(encoding="utf-8", errors="ignore")

                # Count TODO/FIXME/XXX
                todo_count += text.lower().count("todo")
                todo_count += text.lower().count("fixme")
                todo_count += text.lower().count("xxx")

            except Exception:
                continue

    if large_files:
        result["large_files"] = large_files[:10]  # cap output
        result["debt_signals"].append("Large files detected")

    if todo_count > 20:
        result["todo_clusters"] = todo_count
        result["debt_signals"].append(f"High TODO/FIXME density ({todo_count} occurrences)")

    if result["debt_signals"]:
        result["status"] = "completed_with_findings"
    else:
        result["status"] = "completed"

    result["limitations"].append("Static analysis only. No architecture diagrams or runtime profiling.")
    result["limitations"].append("Real technical debt assessment benefits from human review of design.")

    return result
