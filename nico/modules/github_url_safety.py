from __future__ import annotations

import re
from urllib.parse import urlparse

SAFE_REPO_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def parse_github_repo(target: str) -> tuple[str | None, str | None]:
    """Return owner/repo only for canonical github.com repository URLs.

    This intentionally rejects substring host matches such as github.com.evil.test.
    """
    raw = (target or "").strip()
    if not raw:
        return None, None
    candidate = raw if raw.startswith(("http://", "https://")) else "https://" + raw
    try:
        parsed = urlparse(candidate)
    except Exception:
        return None, None
    if parsed.scheme not in {"http", "https"}:
        return None, None
    if (parsed.hostname or "").lower() != "github.com":
        return None, None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None, None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if not SAFE_REPO_PART_RE.fullmatch(owner) or not SAFE_REPO_PART_RE.fullmatch(repo):
        return None, None
    return owner, repo


def is_github_repo_url(target: str) -> bool:
    owner, repo = parse_github_repo(target)
    return bool(owner and repo)
