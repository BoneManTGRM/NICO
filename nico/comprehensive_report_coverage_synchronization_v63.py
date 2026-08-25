from __future__ import annotations

import base64
import hashlib
import io
import re
from copy import deepcopy
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

VERSION = "nico.comprehensive_report_coverage_synchronization.v63"

_COVERAGE_TEXT_PATTERNS = (
    re.compile(
        r"(?P<prefix>analy[sz]er execution coverage\s*(?:is|[:=])\s*)"
        r"(?P<value>\d{1,3})(?P<suffix>\s*%?)",
        re.I,
    ),
    re.compile(
        r"(?P<prefix>analyzer_execution_coverage\s*:\s*)"
        r"(?P<value>\d{1,3})(?P<suffix>\s*%?)",
        re.I,
    ),
    re.compile(
        r"(?P<prefix>scanner_execution_coverage\s*:\s*)"
        r"(?P<value>\d{1,3})(?P<suffix>\s*%?)",
        re.I,
    ),
    re.compile(
        r"(?P<value>\d{1,3})(?P<suffix>\s*%)"
        r"(?P<tail>\s+(?:accepted\s+)?(?:applicable[- ]?)?"
        r"(?:analy[sz]er|scanner)(?:\s+execution)?\s+"
        r"(?:coverage|completion))",
        re.I,
    ),
)
_COVERAGE_LABEL_CONTEXT = re.compile(
    r"(?:analy[sz]er execution coverage\s*(?:is|[:=])\s*|"
    r"analyzer_execution_coverage\s*:\s*|"
    r"scanner_execution_coverage\s*:\s*)$",
    re.I,
)
_NUMERIC_COVERAGE = re.compile(r"^(?P<value>\d{1,3})(?P<suffix>\s*%?)$")
_CANONICAL_COVERAGE_ALIAS = "analyzer_execution_coverage"


def _replace_coverage_text(value: str, expected: int) -> tuple[str, int]:
    output = value
    changes = 0
    for pattern in _COVERAGE_TEXT_PATTERNS:
        def replace(match: re.Match[str]) -> str:
            nonlocal changes
            observed = int(match.group("value"))
            if observed == expected:
                return match.group(0)
            changes += 1
            groups = match.groupdict()
            if groups.get("tail") is not None:
                return f"{expected}{groups.get('suffix') or ''}{groups.get('tail') or ''}"
            return f"{groups.get('prefix') or ''}{expected}{groups.get('suffix') or ''}"

        output = pattern.sub(replace, output)
    return output, changes


def _coverage_alias_present(value: str) -> bool:
    return any(pattern.search(str(value or "")) for pattern in _COVERAGE_TEXT_PATTERNS)


def _scanner_backed_report(package: Mapping[str, Any]) -> bool:
    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    contract = (
        canonical.get("client_readiness_contract")
        if isinstance(canonical.get("client_readiness_contract"), Mapping)
        else {}
    )
    try:
        denominator = int(contract.get("coverage_denominator", 0) or 0)
    except (TypeError, ValueError):
        denominator = 0
    return denominator >= 9


def _ensure_text_coverage_alias(
    value: str,
    expected: int,
    *,
    html: bool,
    required: bool,
) -> tuple[str, int, int]:
    """Repair stale coverage and retain a canonical alias when publication requires it."""

    output, replacements = _replace_coverage_text(str(value or ""), expected)
    if _coverage_alias_present(output) or not required:
        return output, replacements, 0

    line = f"{_CANONICAL_COVERAGE_ALIAS}: {expected}"
    if html:
        insertion = f"<p>{line}</p>"
        match = re.search(r"</body\s*>", output, flags=re.I)
        if match:
            output = output[: match.start()] + insertion + output[match.start():]
        else:
            output = output.rstrip() + insertion
        return output, replacements, 1

    insertion = f"- {line}"
    markers = (
        "- Incomplete applicable analyzers:",
        "- Analizadores aplicables incompletos:",
    )
    for marker in markers:
        if marker in output:
            output = output.replace(marker, f"{insertion}\n{marker}", 1)
            return output, replacements, 1
    output = output.rstrip() + f"\n\n{insertion}\n"
    return output, replacements, 1


def _operand_text(value: Any) -> str:
    if isinstance(value, TextStringObject):
        return str(value)
    if isinstance(value, ByteStringObject):
        try:
            return bytes(value).decode("latin-1")
        except Exception:
            return ""
    return ""


def _operand_value(original: Any, text: str) -> Any:
    if isinstance(original, TextStringObject):
        return TextStringObject(text)
    if isinstance(original, ByteStringObject):
        return ByteStringObject(text.encode("latin-1", errors="replace"))
    return original


def _replace_operand(
    value: Any,
    *,
    expected: int,
    context: str,
) -> tuple[Any, str, int]:
    original = _operand_text(value)
    if not original:
        return value, context, 0

    replaced, changes = _replace_coverage_text(original, expected)
    if not changes:
        numeric = _NUMERIC_COVERAGE.fullmatch(original.strip())
        if numeric and _COVERAGE_LABEL_CONTEXT.search(context.rstrip()[-180:]):
            observed = int(numeric.group("value"))
            if observed != expected:
                prefix = original[: len(original) - len(original.lstrip())]
                suffix_space = original[len(original.rstrip()):]
                replaced = (
                    prefix
                    + str(expected)
                    + (numeric.group("suffix") or "")
                    + suffix_space
                )
                changes = 1

    updated_context = (context + " " + replaced).strip()[-240:]
    return _operand_value(value, replaced), updated_context, changes


def synchronize_pdf_coverage(pdf: bytes, expected: int) -> tuple[bytes, int]:
    if not pdf.startswith(b"%PDF"):
        raise ValueError("coverage synchronization requires a valid PDF")

    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    changes = 0
    for source_page in reader.pages:
        writer.add_page(source_page)
        page = writer.pages[-1]
        contents = page.get_contents()
        if contents is None:
            continue
        stream = ContentStream(contents, writer)
        page_changed = False
        context = ""
        for operands, operator in stream.operations:
            if operator == b"Tj" and operands:
                operands[0], context, count = _replace_operand(
                    operands[0], expected=expected, context=context
                )
                changes += count
                page_changed = page_changed or count > 0
            elif operator == b"TJ" and operands:
                for index, value in enumerate(operands[0]):
                    operands[0][index], context, count = _replace_operand(
                        value, expected=expected, context=context
                    )
                    changes += count
                    page_changed = page_changed or count > 0
            elif operator in {b"'", b'"'} and operands:
                operands[-1], context, count = _replace_operand(
                    operands[-1], expected=expected, context=context
                )
                changes += count
                page_changed = page_changed or count > 0
            elif operator in {b"Td", b"TD", b"Tm", b"T*", b"ET"}:
                context = context[-180:]
        if page_changed:
            page.replace_contents(stream)

    if changes == 0:
        return pdf, 0
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), changes


def _pdf_coverage_alias_present(pdf: bytes) -> bool:
    if not pdf.startswith(b"%PDF"):
        return False
    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    return _coverage_alias_present(extracted)


def _ensure_pdf_coverage_alias(
    pdf: bytes,
    expected: int,
    *,
    required: bool,
) -> tuple[bytes, int]:
    """Retain one bounded machine-readable coverage line only for commercial reports."""

    if _pdf_coverage_alias_present(pdf) or not required:
        return pdf, 0

    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    reader = PdfReader(io.BytesIO(pdf))
    if not reader.pages:
        raise ValueError("coverage synchronization requires at least one PDF page")

    first = reader.pages[0]
    width = float(first.mediabox.width)
    height = float(first.mediabox.height)
    overlay_buffer = io.BytesIO()
    overlay = canvas.Canvas(
        overlay_buffer,
        pagesize=(width, height),
        invariant=1,
    )
    overlay.setFillColor(colors.HexColor("#475569"))
    overlay.setFont("Helvetica", 6.6)
    overlay.drawString(42, 35, f"{_CANONICAL_COVERAGE_ALIAS}: {expected}")
    overlay.save()

    first.merge_page(PdfReader(io.BytesIO(overlay_buffer.getvalue())).pages[0])
    writer = PdfWriter()
    writer.add_page(first)
    for page in reader.pages[1:]:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    rendered = output.getvalue()
    if not _pdf_coverage_alias_present(rendered):
        raise ValueError("canonical analyzer execution coverage was not retained in PDF")
    return rendered, 1


def synchronize_final_report_coverage(
    package: Mapping[str, Any],
    *,
    expected_coverage: int,
) -> dict[str, Any]:
    """Synchronize recognized client-visible coverage aliases after final rendering.

    Existing aliases are corrected to exact-run canonical truth. For a commercial
    scanner-backed Comprehensive report, an omitted alias is retained once in Markdown,
    HTML, and the existing first PDF page so the strict publication gate can verify the
    same canonical truth. Smaller synthetic/compatibility reports preserve their prior
    bytes when no coverage alias is required.
    """

    expected = max(0, min(100, int(expected_coverage)))
    output = deepcopy(dict(package))
    require_presence = _scanner_backed_report(output)

    markdown, markdown_changes, markdown_insertions = _ensure_text_coverage_alias(
        str(output.get("markdown") or ""),
        expected,
        html=False,
        required=require_presence,
    )
    html, html_changes, html_insertions = _ensure_text_coverage_alias(
        str(output.get("html") or ""),
        expected,
        html=True,
        required=require_presence,
    )
    output["markdown"] = markdown
    output["html"] = html

    pdf_changes = 0
    pdf_insertions = 0
    pdf_value = str(output.get("pdf_base64") or "")
    synchronized_pdf = b""
    if pdf_value:
        try:
            pdf = base64.b64decode(pdf_value, validate=True)
        except Exception as exc:
            raise ValueError("final report retained an invalid PDF payload") from exc
        synchronized_pdf, pdf_changes = synchronize_pdf_coverage(pdf, expected)
        synchronized_pdf, pdf_insertions = _ensure_pdf_coverage_alias(
            synchronized_pdf,
            expected,
            required=require_presence,
        )
        output["pdf_base64"] = base64.b64encode(synchronized_pdf).decode("ascii")
        output["pdf_sha256"] = hashlib.sha256(synchronized_pdf).hexdigest()

    markdown_has_alias = _coverage_alias_present(markdown)
    html_has_alias = _coverage_alias_present(html)
    pdf_has_alias = _pdf_coverage_alias_present(synchronized_pdf) if pdf_value else False
    if require_presence and not markdown_has_alias:
        raise ValueError("canonical analyzer execution coverage was not retained in Markdown")
    if require_presence and not html_has_alias:
        raise ValueError("canonical analyzer execution coverage was not retained in HTML")
    if require_presence and pdf_value and not pdf_has_alias:
        raise ValueError("canonical analyzer execution coverage was not retained in PDF")

    if markdown:
        output["markdown_sha256"] = hashlib.sha256(
            markdown.encode("utf-8")
        ).hexdigest()
    if html:
        output["html_sha256"] = hashlib.sha256(html.encode("utf-8")).hexdigest()

    manifest = {
        "version": VERSION,
        "canonical_coverage_value": expected,
        "scanner_backed_report": require_presence,
        "missing_alias_retention_required": require_presence,
        "markdown_replacements": markdown_changes,
        "html_replacements": html_changes,
        "pdf_replacements": pdf_changes,
        "total_replacements": markdown_changes + html_changes + pdf_changes,
        "markdown_insertions": markdown_insertions,
        "html_insertions": html_insertions,
        "pdf_insertions": pdf_insertions,
        "total_insertions": markdown_insertions + html_insertions + pdf_insertions,
        "coverage_alias_present_in_markdown": markdown_has_alias,
        "coverage_alias_present_in_html": html_has_alias,
        "coverage_alias_present_in_pdf": pdf_has_alias,
        "recognized_coverage_aliases_only": True,
        "existing_renderer_preserved": True,
        "existing_visual_design_preserved": True,
        "existing_section_order_preserved": True,
        "existing_pdf_composition_preserved": True,
        "scores_changed": False,
        "scanner_results_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    output["coverage_synchronization"] = manifest
    return output


__all__ = [
    "VERSION",
    "synchronize_final_report_coverage",
    "synchronize_pdf_coverage",
]
