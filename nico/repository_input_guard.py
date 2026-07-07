from __future__ import annotations

from typing import Any

KNOWN_REPOSITORY_SUGGESTIONS = {
    "bonemantgrm/noco": "BoneManTGRM/NICO",
    "bonemantgrm/nicoo": "BoneManTGRM/NICO",
    "bonemantgrm/nico-audit": "BoneManTGRM/NICO",
}


def repository_suggestion(repository: str) -> str | None:
    return KNOWN_REPOSITORY_SUGGESTIONS.get(str(repository or "").strip().lower())


def sanitize_repository_error(repository: str, raw_error: Any) -> dict[str, Any]:
    repo = str(repository or "").strip()
    suggestion = repository_suggestion(repo)
    raw_text = str(raw_error or "")
    status = "not_found" if "404" in raw_text or "not found" in raw_text.lower() else "unavailable"
    message = "Repository metadata unavailable. Check that the repository owner/name is correct and that NICO has access."
    if status == "not_found":
        message = "Repository not found. Check the owner/name spelling or use the full GitHub repository URL."
    if suggestion:
        message = f"Repository not found. Did you mean {suggestion}?"
    return {
        "status": status,
        "repository": repo,
        "message": message,
        "suggested_repository": suggestion,
        "safe_detail": "GitHub raw error details were hidden from the client-facing message.",
    }
