from __future__ import annotations

from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-markdown-identity.v1"
_MARKER = "__nico_comprehensive_markdown_identity_v1__"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _identity_block(canonical: Mapping[str, Any], *, spanish: bool) -> list[str]:
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    repository = _text(identity.get("repository"))
    commit_sha = _text(identity.get("commit_sha"))
    run_id = _text(identity.get("run_id"))
    generated_at = _text(
        identity.get("generated_at")
        or identity.get("generation_timestamp")
        or canonical.get("generated_at")
        or canonical.get("generation_timestamp")
    )
    labels = (
        ("Repositorio", repository),
        ("Commit exacto", commit_sha),
        ("ID de ejecución", run_id),
        ("Generado", generated_at),
    ) if spanish else (
        ("Repository", repository),
        ("Exact commit", commit_sha),
        ("Run ID", run_id),
        ("Generated", generated_at),
    )
    return [f"- {label}: {value}" for label, value in labels if value]


def _ensure_identity_markdown(
    markdown: str,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    source = str(markdown or "").strip()
    block = _identity_block(canonical, spanish=spanish)
    missing = [line for line in block if line.rsplit(": ", 1)[-1] not in source]
    if not missing:
        return source + "\n"
    lines = source.splitlines()
    insert_at = 1 if lines and lines[0].lstrip().startswith("#") else 0
    lines[insert_at:insert_at] = ["", *missing, ""]
    return "\n".join(lines).strip() + "\n"


def install_comprehensive_markdown_identity_v1() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion

    current = completion.compact_client_markdown
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def compact_client_markdown(
        markdown: str,
        canonical: Mapping[str, Any],
        register: Mapping[str, Any],
        *,
        spanish: bool,
    ) -> str:
        rendered = current(
            markdown,
            canonical,
            register,
            spanish=spanish,
        )
        return _ensure_identity_markdown(
            rendered,
            canonical,
            spanish=spanish,
        )

    setattr(compact_client_markdown, _MARKER, True)
    setattr(compact_client_markdown, "_nico_previous", current)
    completion.compact_client_markdown = compact_client_markdown
    return {
        "status": "installed",
        "version": VERSION,
        "repository_identity_required": True,
        "exact_commit_identity_required": True,
        "run_identity_required": True,
        "canonical_generated_at_required": True,
        "markdown_html_identity_parity": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_markdown_identity_v1",
]
