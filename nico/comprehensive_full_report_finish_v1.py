from __future__ import annotations

import ast
import base64
import html
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Iterable, Mapping, Sequence

from pypdf import PdfReader

VERSION = "nico.comprehensive-full-report-finish.v1"
_MARKER = "__nico_comprehensive_full_report_finish_v1__"
_TABLE_MARKER = "__nico_dark_header_paragraph_contrast_v1__"

_DARK_BLUE = "#0c4a6e"
_WHITE = "#ffffff"
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_SUPPORTED_EXTENSIONS = (".csv", ".json", ".html", ".md", ".pdf")
_RAW_MAPPING_LINE = re.compile(
    r"(?m)^\s*(?:[-*]\s+)?\{\s*(?:['\"][^'\"]+['\"]\s*:\s*[^{}\n]+)(?:,\s*['\"][^'\"]+['\"]\s*:\s*[^{}\n]+)*\s*\}\s*$"
)
_NULL_LIKE = {"", "none", "null", "not available", "unknown", "n/a", "na"}

_WORKSHEET_TITLES = (
    "Functional QA",
    "Platform Parity",
    "Historical Trends and Change Failure",
    "Requirements Traceability",
    "Stakeholder and Business Alignment",
    "Risk Reduction and Executive Briefing",
    "Six-Month Roadmap",
    "Staffing, Sequencing, and Cost",
)

_OUTCOME_LABELS = {
    "success": "Successful",
    "successful": "Successful",
    "failure": "Failed",
    "failed": "Failed",
    "cancelled": "Cancelled",
    "canceled": "Cancelled",
    "skipped": "Skipped",
    "timed_out": "Timed out",
    "timeout": "Timed out",
    "unknown": "Unknown",
    "in_progress": "In progress",
    "queued": "In progress",
    "pending": "In progress",
}


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not (candidate.startswith("{") and candidate.endswith("}")):
        return None
    try:
        parsed = ast.literal_eval(candidate)
    except (SyntaxError, ValueError):
        try:
            import json

            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            return None
    return parsed if isinstance(parsed, Mapping) else None


def _label(key: Any) -> str:
    raw = _text(key, 180)
    folded = raw.casefold().replace("-", "_").replace(" ", "_")
    if folded in _OUTCOME_LABELS:
        return _OUTCOME_LABELS[folded]
    return raw.replace("_", " ").replace("-", " ").strip().title() or "Value"


def humanize_structured_value(value: Any) -> str:
    """Render a retained mapping as readable labels without mutating structured JSON."""

    structured = _mapping(value)
    if structured is None:
        return _text(value)
    parts: list[str] = []
    for key, raw in structured.items():
        if isinstance(raw, Mapping):
            rendered = humanize_structured_value(raw)
        elif isinstance(raw, (list, tuple)):
            rendered = ", ".join(humanize_structured_value(item) for item in raw)
        else:
            rendered = _text(raw)
        if rendered:
            parts.append(f"{_label(key)}: {rendered}")
    return "; ".join(parts) or "Not available"


def sanitize_stage_structures(stage: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(stage))
    for field in ("evidence", "findings", "unavailable", "limitations"):
        values = result.get(field)
        if not isinstance(values, (list, tuple)):
            continue
        result[field] = [
            rendered
            for rendered in (humanize_structured_value(item) for item in values)
            if rendered
        ]
    if _mapping(result.get("summary")) is not None:
        result["summary"] = humanize_structured_value(result.get("summary"))
    return result


def _separator_split(text: str, maximum: int, minimum_tail: int = 8) -> int:
    upper = min(maximum, len(text) - minimum_tail)
    if upper <= 0:
        return min(maximum, len(text))
    lower = max(12, upper - 14)
    candidates = [
        index + 1
        for index in range(lower, upper)
        if text[index] in "-_."
    ]
    return candidates[-1] if candidates else upper


def _balanced_chunks(text: str, maximum: int, minimum_tail: int = 8) -> list[str]:
    remainder = text
    chunks: list[str] = []
    while len(remainder) > maximum:
        split_at = _separator_split(remainder, maximum, minimum_tail)
        if split_at <= 1:
            split_at = min(maximum, len(remainder) - minimum_tail)
        chunks.append(remainder[:split_at])
        remainder = remainder[split_at:]
    if remainder:
        chunks.append(remainder)
    if len(chunks) > 1 and len(chunks[-1]) < minimum_tail:
        needed = minimum_tail - len(chunks[-1])
        movable = max(0, len(chunks[-2]) - 12)
        take = min(needed, movable)
        if take:
            chunks[-1] = chunks[-2][-take:] + chunks[-1]
            chunks[-2] = chunks[-2][:-take]
    return [chunk for chunk in chunks if chunk]


def filename_markup(value: Any, maximum: int = 42) -> str:
    raw = _text(value, 900)
    if not raw:
        return "Not available"
    extension = next(
        (suffix for suffix in _SUPPORTED_EXTENSIONS if raw.casefold().endswith(suffix)),
        "",
    )
    stem = raw[: -len(extension)] if extension else raw
    reserve = len(extension)
    chunks = _balanced_chunks(stem, max(18, maximum - reserve) if len(stem) <= maximum else maximum)
    if extension:
        if not chunks:
            chunks = [extension]
        elif len(chunks[-1]) + len(extension) <= maximum:
            chunks[-1] += extension
        else:
            tail_room = max(8, maximum - len(extension))
            last = chunks.pop()
            head, tail = last[:-tail_room], last[-tail_room:]
            if head:
                chunks.append(head)
            chunks.append(tail + extension)
    if len(chunks) > 1 and len(chunks[-1]) == 1:
        chunks[-1] = chunks[-2][-1:] + chunks[-1]
        chunks[-2] = chunks[-2][:-1]
    return "<br/>".join(html.escape(chunk) for chunk in chunks if chunk)


def digest_markup(value: Any) -> str:
    raw = _text(value, 900)
    if _HEX64.fullmatch(raw):
        return f"{html.escape(raw[:32])}<br/>{html.escape(raw[32:])}"
    return html.escape(raw or "Not available")


def _meaningful_timestamp(value: Any) -> str:
    rendered = _text(value, 220)
    return "" if rendered.casefold() in _NULL_LIKE else rendered


def canonical_generation_timestamp(canonical: Mapping[str, Any]) -> str:
    containers: list[Mapping[str, Any]] = []
    for value in (
        canonical.get("identity"),
        canonical,
        canonical.get("run_metadata"),
        canonical.get("report_metadata"),
        canonical.get("metadata"),
        canonical.get("artifact_manifest"),
        canonical.get("assessment"),
    ):
        if isinstance(value, Mapping):
            containers.append(value)
    keys = (
        "generated_at",
        "generation_timestamp",
        "generated_timestamp",
        "report_generated_at",
        "generated",
        "created_at",
        "completed_at",
    )
    for container in containers:
        for key in keys:
            value = _meaningful_timestamp(container.get(key))
            if value:
                return value
    return ""


def _rgb(color: Any) -> tuple[float, float, float] | None:
    try:
        from reportlab.lib import colors

        resolved = colors.toColorOrNone(color)
    except (AttributeError, TypeError, ValueError):
        return None
    if resolved is None:
        return None
    return float(resolved.red), float(resolved.green), float(resolved.blue)


def _is_dark_fill(color: Any) -> bool:
    rgb = _rgb(color)
    if rgb is None:
        return False
    red, green, blue = rgb
    luminance = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
    return luminance <= 0.38


def _set_flowable_white(value: Any) -> None:
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph

    values: Iterable[Any]
    if isinstance(value, (list, tuple)):
        values = value
    else:
        values = (value,)
    for item in values:
        if not isinstance(item, Paragraph):
            continue
        item.style.textColor = colors.white
        for fragment in getattr(item, "frags", ()):
            if hasattr(fragment, "textColor"):
                fragment.textColor = colors.white
        broken = getattr(item, "blPara", None)
        for line in getattr(broken, "lines", ()) if broken is not None else ():
            for fragment in getattr(line, "words", ()):
                if hasattr(fragment, "textColor"):
                    fragment.textColor = colors.white


def enforce_dark_table_contrast(table: Any) -> None:
    """Make every cell covered by a dark fill use white text, including Paragraph fragments."""

    from reportlab.lib import colors

    rows = int(getattr(table, "_nrows", 0) or 0)
    columns = int(getattr(table, "_ncols", 0) or 0)
    if not rows or not columns:
        return
    for command in getattr(table, "_bkgrndcmds", ()):
        if not command or command[0] != "BACKGROUND" or len(command) < 4:
            continue
        _, (start_column, start_row), (end_column, end_row), fill = command
        if not _is_dark_fill(fill):
            continue
        start_column = start_column + columns if start_column < 0 else start_column
        end_column = end_column + columns if end_column < 0 else end_column
        start_row = start_row + rows if start_row < 0 else start_row
        end_row = end_row + rows if end_row < 0 else end_row
        for row in range(max(0, start_row), min(rows - 1, end_row) + 1):
            for column in range(max(0, start_column), min(columns - 1, end_column) + 1):
                table._cellStyles[row][column].color = colors.white
                _set_flowable_white(table._cellvalues[row][column])


def assert_dark_table_contrast(table: Any) -> None:
    from reportlab.lib import colors

    rows = int(getattr(table, "_nrows", 0) or 0)
    columns = int(getattr(table, "_ncols", 0) or 0)
    for command in getattr(table, "_bkgrndcmds", ()):
        if not command or command[0] != "BACKGROUND" or len(command) < 4:
            continue
        _, (start_column, start_row), (end_column, end_row), fill = command
        if not _is_dark_fill(fill):
            continue
        start_column = start_column + columns if start_column < 0 else start_column
        end_column = end_column + columns if end_column < 0 else end_column
        start_row = start_row + rows if start_row < 0 else start_row
        end_row = end_row + rows if end_row < 0 else end_row
        for row in range(max(0, start_row), min(rows - 1, end_row) + 1):
            for column in range(max(0, start_column), min(columns - 1, end_column) + 1):
                color = table._cellStyles[row][column].color
                if _rgb(color) != _rgb(colors.white):
                    raise ValueError("dark table cell does not use white foreground text")
                cell = table._cellvalues[row][column]
                values = cell if isinstance(cell, (list, tuple)) else (cell,)
                for item in values:
                    for fragment in getattr(item, "frags", ()):
                        if _rgb(getattr(fragment, "textColor", None)) != _rgb(colors.white):
                            raise ValueError("dark table Paragraph fragment does not use white text")


def install_reportlab_dark_header_contrast() -> bool:
    from reportlab.platypus import Table

    current = Table.setStyle
    if getattr(current, _TABLE_MARKER, False):
        return False

    @wraps(current)
    def set_style(table: Any, style: Any, **kwargs: Any) -> Any:
        result = current(table, style, **kwargs)
        enforce_dark_table_contrast(table)
        return result

    setattr(set_style, _TABLE_MARKER, True)
    setattr(set_style, "_nico_previous", current)
    Table.setStyle = set_style
    return True


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)


def _strip_html(rendered_html: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "\n", rendered_html or ""))


def assert_no_raw_mapping_presentation(markdown: str, rendered_html: str, pdf: bytes) -> None:
    surfaces = (markdown or "", _strip_html(rendered_html), _pdf_text(pdf))
    for surface in surfaces:
        if _RAW_MAPPING_LINE.search(surface):
            raise ValueError("client-facing artifact retained a raw mapping presentation")


def _assessment(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    value = canonical.get("assessment")
    return value if isinstance(value, Mapping) else {}


def _stage_titles(canonical: Mapping[str, Any]) -> set[str]:
    stages = canonical.get("stage_summaries")
    if not isinstance(stages, list):
        stages = _assessment(canonical).get("stage_summaries")
    return {
        _text(item.get("title"), 300)
        for item in stages or []
        if isinstance(item, Mapping) and _text(item.get("title"), 300)
    }


def _score_sections(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    sections = _assessment(canonical).get("sections")
    return [item for item in sections or [] if isinstance(item, Mapping)]


def _scanner_records(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records = canonical.get("scanner_execution_records")
    if not isinstance(records, list):
        records = _assessment(canonical).get("scanner_execution_records")
    return [item for item in records or [] if isinstance(item, Mapping)]


def _candidate_register(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    assessment = _assessment(canonical)
    for value in (
        assessment.get("canonical_scanner_finding_register"),
        canonical.get("canonical_scanner_finding_register"),
        assessment.get("review_candidate_register"),
        canonical.get("review_candidate_register"),
    ):
        if isinstance(value, Mapping):
            return value
    return {}


def _candidate_total(canonical: Mapping[str, Any]) -> int:
    assessment = _assessment(canonical)
    for value in (
        canonical.get("review_candidate_summary"),
        assessment.get("review_candidate_summary"),
    ):
        if not isinstance(value, Mapping):
            continue
        for key in ("review_required_total", "raw_total", "candidate_total"):
            raw = value.get(key)
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                return max(0, int(raw))
    findings = _candidate_register(canonical).get("findings")
    return len(findings) if isinstance(findings, list) else 0


def _exact_source_findings(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    register = canonical.get("client_finding_remediation_register")
    if isinstance(register, Mapping):
        code = register.get("code_findings")
        if isinstance(code, list):
            return [item for item in code if isinstance(item, Mapping)]
    findings = canonical.get("canonical_findings")
    return [item for item in findings or [] if isinstance(item, Mapping)]


def _fixture_identity(canonical: Mapping[str, Any]) -> bool:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    joined = " ".join(
        _text(identity.get(key) or canonical.get(key), 300).casefold()
        for key in ("customer_id", "project_id", "run_id")
    )
    return any(token in joined for token in ("fixture", "phase9-proof", "test-customer", "test-project"))


def classify_report_proof(canonical: Mapping[str, Any]) -> str:
    """Distinguish renderer fixtures from evidence-rich Comprehensive packages."""

    signals = 0
    titles = _stage_titles(canonical)
    if _score_sections(canonical):
        signals += 1
    if set(_WORKSHEET_TITLES).issubset(titles):
        signals += 2
    if _scanner_records(canonical) or _candidate_register(canonical):
        signals += 1
    if isinstance(canonical.get("artifact_manifest"), Mapping) and isinstance(canonical.get("approval"), Mapping):
        signals += 1
    if len(titles) >= 12:
        signals += 1
    return "full_comprehensive" if signals >= 4 and not _fixture_identity(canonical) else "sparse_fixture"


def assert_full_data_parity(
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> dict[str, Any]:
    if classify_report_proof(canonical) != "full_comprehensive":
        raise ValueError("sparse fixture cannot satisfy full-data Comprehensive parity validation")
    extracted = _pdf_text(pdf)
    combined = "\n".join((markdown or "", _strip_html(rendered_html), extracted))
    sections = _score_sections(canonical)
    if not sections:
        raise ValueError("full-data proof is missing the canonical scorecard")
    titles = _stage_titles(canonical)
    missing_worksheets = [title for title in _WORKSHEET_TITLES if title not in titles or title not in combined]
    if missing_worksheets:
        raise ValueError("full-data proof is missing human-review worksheets: " + ", ".join(missing_worksheets))
    scanners = _scanner_records(canonical)
    requested = _assessment(canonical).get("requested_scanner_records") or canonical.get("requested_scanner_records")
    if requested and not scanners:
        raise ValueError("full-data proof is missing applicable scanner execution evidence")
    candidates = _candidate_total(canonical)
    if candidates and not _candidate_register(canonical):
        raise ValueError("full-data proof has candidates but no canonical candidate register")
    if candidates and "Review-Required Candidate Register" not in combined:
        raise ValueError("full-data PDF is missing the candidate register section")
    findings = _exact_source_findings(canonical)
    missing_findings: list[str] = []
    for finding in findings:
        identifier = _text(finding.get("finding_id") or finding.get("id"), 300)
        if identifier and identifier not in extracted:
            missing_findings.append(identifier)
    if missing_findings:
        raise ValueError(
            f"full-data PDF index omitted {len(missing_findings)} canonical exact-source finding(s)"
        )
    for title in (
        "Client Artifact Manifest",
        "Human Review and Exact-Artifact Approval Record",
        "Human Review and Acceptance Gate",
        "Complete Exact-Source Index",
    ):
        if title not in extracted:
            raise ValueError(f"full-data PDF is missing required section: {title}")
    timestamp = canonical_generation_timestamp(canonical)
    if not timestamp:
        raise ValueError("full-data manifest is missing a canonical generation timestamp")
    if "Generated\nNot available" in extracted or "Generated: Not available" in extracted:
        raise ValueError("full-data manifest silently degraded the generation timestamp")
    return {
        "proof_kind": "full_comprehensive",
        "scored_control_count": len(sections),
        "scanner_execution_count": len(scanners),
        "candidate_count": candidates,
        "exact_source_finding_count": len(findings),
        "worksheet_count": len(_WORKSHEET_TITLES),
        "generation_timestamp": timestamp,
    }


def assert_exact_artifact_binding(result: Mapping[str, Any]) -> None:
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    if classify_report_proof(canonical) != "full_comprehensive":
        return
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    run_id = _text(identity.get("run_id") or canonical.get("run_id"), 300)
    commit = _text(identity.get("commit_sha") or canonical.get("commit_sha"), 120)
    manifest = result.get("evidence_manifest") or result.get("detached_evidence_manifest") or canonical.get("artifact_manifest")
    if not isinstance(manifest, Mapping):
        raise ValueError("full-data proof is missing the detached evidence manifest")
    entries = manifest.get("artifacts") or manifest.get("entries") or []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        entry_run = _text(entry.get("run_id"), 300)
        entry_commit = _text(entry.get("commit_sha"), 120)
        if run_id and entry_run and entry_run != run_id:
            raise ValueError("companion artifact run ID does not match the canonical run")
        if commit and entry_commit and entry_commit != commit:
            raise ValueError("companion artifact commit does not match the canonical commit")


def install_comprehensive_full_report_finish_v1() -> dict[str, Any]:
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup
    from nico import comprehensive_manifest_navigation_v1 as navigation

    install_reportlab_dark_header_contrast()
    cleanup._filename_markup = filename_markup
    cleanup._digest_markup = digest_markup

    current_stage = cleanup.sanitize_rendered_stage
    if not getattr(current_stage, _MARKER, False):
        @wraps(current_stage)
        def sanitize_stage(stage: Mapping[str, Any]) -> dict[str, Any]:
            return current_stage(sanitize_stage_structures(stage))

        setattr(sanitize_stage, _MARKER, True)
        setattr(sanitize_stage, "_nico_previous", current_stage)
        cleanup.sanitize_rendered_stage = sanitize_stage

    current_identity = manifest._canonical_identity
    if not getattr(current_identity, _MARKER, False):
        @wraps(current_identity)
        def canonical_identity(canonical: Mapping[str, Any]) -> dict[str, str]:
            result = dict(current_identity(canonical))
            timestamp = canonical_generation_timestamp(canonical)
            if timestamp:
                result["generation_timestamp"] = timestamp
            return result

        setattr(canonical_identity, _MARKER, True)
        setattr(canonical_identity, "_nico_previous", current_identity)
        manifest._canonical_identity = canonical_identity

    current_assert = cleanup.assert_human_review_package_cleanup
    if not getattr(current_assert, _MARKER, False):
        @wraps(current_assert)
        def assert_cleanup(
            canonical: Mapping[str, Any],
            markdown: str,
            rendered_html: str,
            pdf: bytes,
        ) -> None:
            current_assert(canonical, markdown, rendered_html, pdf)
            assert_no_raw_mapping_presentation(markdown, rendered_html, pdf)
            if classify_report_proof(canonical) == "full_comprehensive":
                assert_full_data_parity(canonical, markdown, rendered_html, pdf)

        setattr(assert_cleanup, _MARKER, True)
        setattr(assert_cleanup, "_nico_previous", current_assert)
        cleanup.assert_human_review_package_cleanup = assert_cleanup

    current_final = navigation._validate_final_package
    if not getattr(current_final, _MARKER, False):
        @wraps(current_final)
        def validate_final(result: Mapping[str, Any]) -> None:
            current_final(result)
            assert_exact_artifact_binding(result)

        setattr(validate_final, _MARKER, True)
        setattr(validate_final, "_nico_previous", current_final)
        navigation._validate_final_package = validate_final

    return {
        "status": "installed",
        "version": VERSION,
        "dark_table_text": _WHITE,
        "dark_table_background_preserved": _DARK_BLUE,
        "manifest_filename_wrapping_bound": True,
        "manifest_digest_32_32_bound": True,
        "canonical_generation_timestamp_bound": True,
        "raw_mapping_presentation_blocked": True,
        "sparse_fixture_cannot_satisfy_full_data_proof": True,
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_WORKSHEET_TITLES",
    "assert_dark_table_contrast",
    "assert_exact_artifact_binding",
    "assert_full_data_parity",
    "assert_no_raw_mapping_presentation",
    "canonical_generation_timestamp",
    "classify_report_proof",
    "digest_markup",
    "enforce_dark_table_contrast",
    "filename_markup",
    "humanize_structured_value",
    "install_comprehensive_full_report_finish_v1",
    "install_reportlab_dark_header_contrast",
    "sanitize_stage_structures",
]
