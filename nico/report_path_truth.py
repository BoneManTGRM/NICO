from __future__ import annotations

from typing import Any

REPORT_PATHS = {
    "express": {
        "label": "Express Assessment",
        "other_label": "Full Assessment",
    },
    "full_run": {
        "label": "Full Assessment",
        "other_label": "Express Assessment",
    },
}


def _banner_text(path: str, label: str, other_label: str) -> str:
    return f"Report path: {label} (`{path}`). This is not {other_label} output."


def _label_markdown(markdown: Any, path: str, label: str, other_label: str) -> Any:
    if not isinstance(markdown, str) or not markdown.strip():
        return markdown
    marker = f"Report path: {label}"
    if marker in markdown:
        return markdown
    return f"> {_banner_text(path, label, other_label)}\n\n{markdown}"


def _label_html(html: Any, path: str, label: str, other_label: str) -> Any:
    if not isinstance(html, str) or not html.strip():
        return html
    marker = f'data-nico-report-path="{path}"'
    if marker in html:
        return html
    banner = (
        f'<aside data-nico-report-path="{path}" style="margin:12px 0;padding:12px;border:1px solid #38bdf8;'
        'border-radius:10px;background:#e0f2fe;color:#0c4a6e;font-weight:700">'
        f'{_banner_text(path, label, other_label).replace(f"`{path}`", f"<code>{path}</code>")}'
        '</aside>'
    )
    lower = html.lower()
    body_index = lower.find("<body")
    if body_index >= 0:
        close_index = html.find(">", body_index)
        if close_index >= 0:
            return html[: close_index + 1] + banner + html[close_index + 1 :]
    return banner + html


def _observed_paths(result: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    for candidate in (
        result.get("report_path"),
        result.get("reports", {}).get("report_path") if isinstance(result.get("reports"), dict) else None,
        result.get("assessment", {}).get("report_path") if isinstance(result.get("assessment"), dict) else None,
    ):
        value = str(candidate or "").strip()
        if value and value not in observed:
            observed.append(value)
    return observed


def apply_report_path_truth(result: dict[str, Any], expected_path: str) -> dict[str, Any]:
    """Apply one canonical report path and disclose any pre-existing mismatch.

    A mismatch never becomes client-ready merely because the expected label is
    repaired. It remains human-review-bound with an explicit conflict record.
    """

    config = REPORT_PATHS.get(expected_path)
    if config is None:
        raise ValueError(f"unsupported report path: {expected_path}")

    label = config["label"]
    other_label = config["other_label"]
    conflicts = [value for value in _observed_paths(result) if value != expected_path]

    result["report_path"] = expected_path
    result["report_path_label"] = label

    reports = result.get("reports")
    if isinstance(reports, dict):
        reports["report_path"] = expected_path
        reports["report_path_label"] = label
        reports["markdown"] = _label_markdown(reports.get("markdown"), expected_path, label, other_label)
        reports["html"] = _label_html(reports.get("html"), expected_path, label, other_label)

    assessment = result.get("assessment")
    if isinstance(assessment, dict):
        assessment["report_path"] = expected_path
        assessment["report_path_label"] = label

    if conflicts:
        conflict = {
            "detected": True,
            "expected": expected_path,
            "observed": conflicts,
            "message": "Conflicting report-path metadata was corrected to the endpoint's canonical path and requires human review.",
        }
        result["report_path_conflict"] = conflict
        result["human_review_required"] = True
        result["client_ready"] = False
        if isinstance(reports, dict):
            reports["report_path_conflict"] = conflict
        if isinstance(assessment, dict):
            assessment["report_path_conflict"] = conflict
    else:
        result.pop("report_path_conflict", None)

    return result
