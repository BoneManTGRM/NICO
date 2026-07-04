"""Repo Intake Module (Phase 2)

Basic but functional intake for both URLs and local paths.
"""

from pathlib import Path
import re


def intake(target: str) -> dict:
    result = {
        "target": target,
        "type": None,
        "is_url": False,
        "is_local_path": False,
        "exists": False,
        "metadata": {},
        "limitations": []
    }

    # Detect if it looks like a GitHub URL
    github_url_pattern = r"https?://(www\.)?github\.com/[^/]+/[^/]+"
    if re.match(github_url_pattern, target):
        result["type"] = "github_url"
        result["is_url"] = True
        result["metadata"]["platform"] = "github"
    elif target.startswith(("http://", "https://")):
        result["type"] = "other_url"
        result["is_url"] = True
        result["limitations"].append("Only GitHub URLs are fully supported in current version")
    else:
        # Treat as local path
        result["type"] = "local_path"
        result["is_local_path"] = True
        path = Path(target).expanduser().resolve()
        result["exists"] = path.exists()

        if result["exists"]:
            result["metadata"]["absolute_path"] = str(path)
            if path.is_dir():
                result["metadata"]["is_directory"] = True
                # Count files (shallow)
                try:
                    files = list(path.rglob("*"))
                    result["metadata"]["file_count"] = len([f for f in files if f.is_file()])
                except Exception:
                    result["limitations"].append("Could not count files in directory")
            else:
                result["metadata"]["is_file"] = True
        else:
            result["limitations"].append("Local path does not exist")

    if not result["is_url"] and not result["is_local_path"]:
        result["limitations"].append("Target format not recognized")

    return result
