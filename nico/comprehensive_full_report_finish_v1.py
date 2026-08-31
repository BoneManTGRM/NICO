from __future__ import annotations

import ast
import base64
import html
import io
import json
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive-full-report-finish.v1"
_MARKER = "__nico_comprehensive_full_report_finish_v1__"
_TABLE_MARKER = "__nico_dark_header_paragraph_contrast_v1__"
_DARK_BLUE = "#0c4a6e"
_WHITE = "#ffffff"
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_EXTENSIONS = (".csv", ".json", ".html", ".md", ".pdf")
_NULLISH = {"", "none", "null", "not available", "unknown", "n/a", "na"}
_INTERNAL_PROPERTY_LINE = re.compile(
    r"^(?:(?:scope|capability|state|status|source|review)|"
    r"[a-z][a-z0-9_.\[\]]*[_\.\[][a-z0-9_.\[\]]*)\s*:",
)

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
    text = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _parse_mapping(value: Any) -> Mapping[str, Any] | None:
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
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            return None
    return parsed if isinstance(parsed, Mapping) else None


def _mapping_tail(value: Any) -> tuple[str, Mapping[str, Any] | None]:
    direct = _parse_mapping(value)
    if direct is not None:
        return "", direct
    if not isinstance(value, str):
        return "", None
    candidate = value.strip()
    opening = candidate.find("{")
    if opening <= 0 or not candidate.endswith("}"):
        return "", None
    prefix = candidate[:opening].strip()
    if not prefix.endswith((":", "=")):
        return "", None
    return prefix.rstrip(":= "), _parse_mapping(candidate[opening:])


def _label(value: Any) -> str:
    raw = _text(value, 180)
    key = raw.casefold().replace("-", "_").replace(" ", "_")
    return _OUTCOME_LABELS.get(
        key, raw.replace("_", " ").replace("-", " ").strip().title() or "Value"
    )


def _render_mapping(value: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key, raw in value.items():
        if isinstance(raw, Mapping):
            rendered = _render_mapping(raw)
        elif isinstance(raw, (list, tuple)):
            rendered = ", ".join(humanize_structured_value(item) for item in raw)
        else:
            rendered = _text(raw)
        if rendered:
            parts.append(f"{_label(key)}: {rendered}")
    return "; ".join(parts) or "Not available"


def humanize_structured_value(value: Any) -> str:
    """Turn a retained mapping into readable labels without changing canonical JSON."""

    prefix, structured = _mapping_tail(value)
    if structured is None:
        return _text(value)
    rendered = _render_mapping(structured)
    if not prefix:
        return rendered
    return f"{_label(prefix.rsplit('.', 1)[-1])}: {rendered}"


def sanitize_stage_structures(stage: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(stage))
    for field in ("evidence", "findings", "unavailable", "limitations"):
        values = result.get(field)
        if isinstance(values, (list, tuple)):
            result[field] = [
                line
                for line in (humanize_structured_value(item) for item in values)
                if line
            ]
    if _mapping_tail(result.get("summary"))[1] is not None:
        result["summary"] = humanize_structured_value(result.get("summary"))
    return result


def _chunks(value: str, maximum: int, minimum_tail: int = 8) -> list[str]:
    output: list[str] = []
    remainder = value
    while len(remainder) > maximum:
        upper = min(maximum, len(remainder) - minimum_tail)
        lower = max(12, upper - 14)
        breaks = [i + 1 for i in range(lower, upper) if remainder[i] in "-_."]
        split = breaks[-1] if breaks else upper
        output.append(remainder[:split])
        remainder = remainder[split:]
    if remainder:
        output.append(remainder)
    if len(output) > 1 and len(output[-1]) < minimum_tail:
        need = minimum_tail - len(output[-1])
        take = min(need, max(0, len(output[-2]) - 12))
        if take:
            output[-1] = output[-2][-take:] + output[-1]
            output[-2] = output[-2][:-take]
    return [item for item in output if item]


def filename_markup(value: Any, maximum: int = 42) -> str:
    raw = _text(value, 900)
    if not raw:
        return "Not available"
    extension = next((ext for ext in _EXTENSIONS if raw.casefold().endswith(ext)), "")
    stem = raw[: -len(extension)] if extension else raw
    chunks = _chunks(stem, maximum)
    if extension:
        if chunks and len(chunks[-1]) + len(extension) <= maximum:
            chunks[-1] += extension
        else:
            last = chunks.pop() if chunks else ""
            room = max(8, maximum - len(extension))
            if len(last) > room:
                chunks.append(last[:-room])
                last = last[-room:]
            chunks.append(last + extension)
    return "<br/>".join(html.escape(item) for item in chunks if item)


def digest_markup(value: Any) -> str:
    raw = _text(value, 900)
    if _HEX64.fullmatch(raw):
        return f"{raw[:32]}<br/>{raw[32:]}"
    return html.escape(raw or "Not available")


def canonical_generation_timestamp(canonical: Mapping[str, Any]) -> str:
    containers = (
        canonical.get("identity"),
        canonical,
        canonical.get("run_metadata"),
        canonical.get("report_metadata"),
        canonical.get("metadata"),
        canonical.get("artifact_manifest"),
        canonical.get("assessment"),
    )
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
        if not isinstance(container, Mapping):
            continue
        for key in keys:
            value = _text(container.get(key), 220)
            if value and value.casefold() not in _NULLISH:
                return value
    return ""


def _rgb(value: Any) -> tuple[float, float, float] | None:
    from reportlab.lib import colors

    try:
        color = colors.toColorOrNone(value)
    except (AttributeError, TypeError, ValueError):
        return None
    return None if color is None else (float(color.red), float(color.green), float(color.blue))


def _dark(value: Any) -> bool:
    color = _rgb(value)
    if color is None:
        return False
    red, green, blue = color
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue <= 0.38


def _cell_range(table: Any, start: tuple[int, int], end: tuple[int, int]):
    rows, columns = table._nrows, table._ncols
    start_column, start_row = start
    end_column, end_row = end
    start_column = start_column + columns if start_column < 0 else start_column
    end_column = end_column + columns if end_column < 0 else end_column
    start_row = start_row + rows if start_row < 0 else start_row
    end_row = end_row + rows if end_row < 0 else end_row
    for row in range(max(0, start_row), min(rows - 1, end_row) + 1):
        for column in range(max(0, start_column), min(columns - 1, end_column) + 1):
            yield row, column


def _paragraph_fragments(value: Any):
    values = value if isinstance(value, (list, tuple)) else (value,)
    for item in values:
        for fragment in getattr(item, "frags", ()):
            yield fragment
        broken = getattr(item, "blPara", None)
        for line in getattr(broken, "lines", ()) if broken is not None else ():
            yield from getattr(line, "words", ())


def enforce_dark_table_contrast(table: Any) -> None:
    from reportlab.lib import colors

    for command in getattr(table, "_bkgrndcmds", ()):
        if len(command) < 4 or command[0] != "BACKGROUND" or not _dark(command[3]):
            continue
        for row, column in _cell_range(table, command[1], command[2]):
            table._cellStyles[row][column].color = colors.white
            for fragment in _paragraph_fragments(table._cellvalues[row][column]):
                if hasattr(fragment, "textColor"):
                    fragment.textColor = colors.white


def assert_dark_table_contrast(table: Any) -> None:
    from reportlab.lib import colors

    white = _rgb(colors.white)
    for command in getattr(table, "_bkgrndcmds", ()):
        if len(command) < 4 or command[0] != "BACKGROUND" or not _dark(command[3]):
            continue
        for row, column in _cell_range(table, command[1], command[2]):
            if _rgb(table._cellStyles[row][column].color) != white:
                raise ValueError("dark table cell does not use white foreground text")
            for fragment in _paragraph_fragments(table._cellvalues[row][column]):
                if _rgb(getattr(fragment, "textColor", None)) != white:
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


def _html_text(rendered_html: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "\n", rendered_html or ""))


def assert_no_raw_mapping_presentation(markdown: str, rendered_html: str, pdf: bytes) -> None:
    for surface in (markdown or "", _html_text(rendered_html), _pdf_text(pdf)):
        for raw_line in surface.splitlines():
            line = raw_line.strip()
            if line.startswith(("- ", "* ")):
                line = line[2:].strip()
            line = line.lstrip("•").strip()
            if _mapping_tail(line)[1] is not None:
                raise ValueError(
                    "client-facing artifact retained a raw mapping presentation"
                )
            if _INTERNAL_PROPERTY_LINE.match(line):
                raise ValueError(
                    "client-facing artifact retained an internal property presentation"
                )


def _assessment(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    value = canonical.get("assessment")
    return value if isinstance(value, Mapping) else {}


def _stages(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = canonical.get("stage_summaries")
    if not isinstance(values, list):
        values = _assessment(canonical).get("stage_summaries")
    return [item for item in values or [] if isinstance(item, Mapping)]


def _sections(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in _assessment(canonical).get("sections") or [] if isinstance(item, Mapping)]


def _scanners(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = canonical.get("scanner_execution_records")
    if not isinstance(values, list):
        values = _assessment(canonical).get("scanner_execution_records")
    return [item for item in values or [] if isinstance(item, Mapping)]


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
    for summary in (
        canonical.get("review_candidate_summary"),
        _assessment(canonical).get("review_candidate_summary"),
    ):
        if not isinstance(summary, Mapping):
            continue
        for key in ("review_required_total", "raw_total", "candidate_total"):
            value = summary.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return max(0, int(value))
    findings = _candidate_register(canonical).get("findings")
    return len(findings) if isinstance(findings, list) else 0


def _findings(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    register = canonical.get("client_finding_remediation_register")
    if isinstance(register, Mapping) and isinstance(register.get("code_findings"), list):
        return [item for item in register["code_findings"] if isinstance(item, Mapping)]
    return [item for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)]


def classify_report_proof(canonical: Mapping[str, Any]) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    identity_text = " ".join(
        _text(identity.get(key) or canonical.get(key), 300).casefold()
        for key in ("customer_id", "project_id", "run_id")
    )
    if any(value in identity_text for value in ("fixture", "phase9-proof", "test-customer", "test-project")):
        return "sparse_fixture"
    titles = {_text(item.get("title"), 300) for item in _stages(canonical)}
    signals = int(bool(_sections(canonical)))
    signals += 2 if set(_WORKSHEET_TITLES).issubset(titles) else 0
    signals += int(bool(_scanners(canonical) or _candidate_register(canonical)))
    signals += int(
        isinstance(canonical.get("artifact_manifest"), Mapping)
        and isinstance(canonical.get("approval"), Mapping)
    )
    signals += int(len(titles) >= 12)
    return "full_comprehensive" if signals >= 4 else "sparse_fixture"


def assert_full_data_parity(
    canonical: Mapping[str, Any], markdown: str, rendered_html: str, pdf: bytes
) -> dict[str, Any]:
    if classify_report_proof(canonical) != "full_comprehensive":
        raise ValueError("sparse fixture cannot satisfy full-data Comprehensive parity validation")
    extracted = _pdf_text(pdf)
    combined = "\n".join((markdown or "", _html_text(rendered_html), extracted))
    sections = _sections(canonical)
    if not sections:
        raise ValueError("full-data proof is missing the canonical scorecard")
    titles = {_text(item.get("title"), 300) for item in _stages(canonical)}
    missing = [title for title in _WORKSHEET_TITLES if title not in titles or title not in combined]
    if missing:
        raise ValueError("full-data proof is missing human-review worksheets: " + ", ".join(missing))
    scanners = _scanners(canonical)
    requested = _assessment(canonical).get("requested_scanner_records") or canonical.get("requested_scanner_records")
    if requested and not scanners:
        raise ValueError("full-data proof is missing applicable scanner execution evidence")
    candidates = _candidate_total(canonical)
    if candidates and not _candidate_register(canonical):
        raise ValueError("full-data proof has candidates but no canonical candidate register")
    if candidates and "Review-Required Candidate Register" not in combined:
        raise ValueError("full-data PDF is missing the candidate register section")
    findings = _findings(canonical)
    omitted = [
        _text(item.get("finding_id") or item.get("id"), 300)
        for item in findings
        if _text(item.get("finding_id") or item.get("id"), 300) not in extracted
    ]
    if omitted:
        raise ValueError(f"full-data PDF index omitted {len(omitted)} canonical exact-source finding(s)")
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
    manifest = result.get("artifact_manifest") or canonical.get("artifact_manifest")
    if not isinstance(manifest, Mapping):
        raise ValueError("full-data proof is missing the detached evidence manifest")
    for entry in manifest.get("artifacts") or manifest.get("entries") or []:
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
            canonical: Mapping[str, Any], markdown: str, rendered_html: str, pdf: bytes
        ) -> None:
            current_assert(canonical, markdown, rendered_html, pdf)
            assert_no_raw_mapping_presentation(markdown, rendered_html, pdf)

        setattr(assert_cleanup, _MARKER, True)
        setattr(assert_cleanup, "_nico_previous", current_assert)
        cleanup.assert_human_review_package_cleanup = assert_cleanup

    current_final = navigation._validate_final_package
    if not getattr(current_final, _MARKER, False):
        @wraps(current_final)
        def validate_final(result: Mapping[str, Any]) -> None:
            current_final(result)
            canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
            if classify_report_proof(canonical) == "full_comprehensive":
                assert_full_data_parity(
                    canonical,
                    str(result.get("markdown") or ""),
                    str(result.get("html") or ""),
                    base64.b64decode(str(result.get("pdf_base64") or ""), validate=True),
                )
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
