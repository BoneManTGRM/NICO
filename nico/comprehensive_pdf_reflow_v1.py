from __future__ import annotations

import html
import io
import re
from typing import Any

VERSION = "nico.comprehensive_pdf_reflow.v1.1"

_HEADER = re.compile(r"^NICO\s+Comprehensive\b.*AUTOMATED\s+DRAFT", re.I)
_DOCUMENT_PAGE = re.compile(r"^Document\s+page\s+\d+\s+of\s+\d+$", re.I)
_LOCAL_PAGE = re.compile(r"^(?:Page|Página)\s+\d+(?:\s+of\s+\d+)?$", re.I)

# Never re-render legal/review/manifest/index pages. These are intentionally isolated
# because their visual structure carries approval, integrity, or exact-source meaning.
_EXCLUDED_TITLE_TOKENS = (
    "table of contents",
    "executive decision brief",
    "priority constraints",
    "comprehensive technical assessment",
    "review-required candidate register",
    "compact finding",
    "complete exact-source index",
    "human review",
    "approval record",
    "client artifact manifest",
    "exact-artifact",
    "tabla de contenido",
    "resumen ejecutivo",
    "registro de candidatos",
    "registro compacto",
    "índice completo",
    "revisión humana",
    "registro de aprobación",
    "manifiesto",
)

_LIMITATION_MARKERS = (
    "unavailable or limited evidence",
    "evidence limitations",
    "unavailable evidence",
    "evidencia no disponible",
    "evidencia limitada",
    "limitaciones de evidencia",
)


def _normal(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _page_text(page: Any) -> str:
    try:
        return str(page.extract_text() or "")
    except Exception:
        return ""


def _content_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in str(text or "").splitlines():
        line = _normal(raw)
        if not line:
            continue
        if _HEADER.match(line) or _DOCUMENT_PAGE.match(line) or _LOCAL_PAGE.match(line):
            continue
        if line.startswith("NICO | evidence-bound technical review package"):
            continue
        if line.startswith("NICO · compact finding register"):
            continue
        lines.append(line)
    return lines


def _title(text: str) -> str:
    lines = _content_lines(text)
    return lines[0] if lines else ""


def _has_standard_header(text: str) -> bool:
    return any(_HEADER.match(_normal(line)) for line in str(text or "").splitlines())


def _ordinary_sparse_stage(text: str) -> bool:
    normalized = _normal(text)
    if not _has_standard_header(text) or not (120 <= len(normalized) <= 1_900):
        return False
    title = _title(text)
    if not title or title.startswith(("-", "•")) or len(title) > 125:
        return False
    folded = title.casefold()
    if any(token in folded for token in _EXCLUDED_TITLE_TOKENS):
        return False
    # A normal report section title is descriptive prose, not a raw retained-evidence
    # key/value line. This keeps the compactor away from continuation fragments unless
    # they are handled by the bounded limitation continuation rule below.
    if re.search(r"\b(?:true|false|pending|not_supplied)\b", folded) and ":" in title:
        return False
    return True


def _ultra_sparse_limitation_start(text: str) -> bool:
    normalized = _normal(text).casefold()
    return (
        _has_standard_header(text)
        and len(normalized) <= 750
        and any(marker in normalized for marker in _LIMITATION_MARKERS)
    )


def _ultra_sparse_continuation(text: str) -> bool:
    normalized = _normal(text)
    if not _has_standard_header(text) or len(normalized) > 750:
        return False
    title = _title(text).casefold()
    if any(token in title for token in _EXCLUDED_TITLE_TOKENS):
        return False
    return True


def _groups(texts: list[str]) -> list[tuple[int, int]]:
    groups: list[tuple[int, int]] = []

    # Compact consecutive ordinary one-section pages. These are the source of the
    # seven-page control-score run and five-page evidence-foundation run seen in the
    # production 44-page artifact. A group is accepted only if every meaningful line
    # survives exact text-preservation verification after re-rendering.
    start: int | None = None
    flags = [_ordinary_sparse_stage(text) for text in texts]
    for index, flag in enumerate(flags + [False]):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            if index - start >= 2:
                groups.append((start, index))
            start = None

    # Compact a sparse limitation page plus immediately following sparse continuation
    # pages even when the continuation no longer repeats the section heading. This is
    # the exact pattern that left Roadmap and Staffing fragments on separate pages.
    index = 0
    while index < len(texts):
        if not _ultra_sparse_limitation_start(texts[index]):
            index += 1
            continue
        end = index + 1
        while end < len(texts) and _ultra_sparse_continuation(texts[end]):
            end += 1
        if end - index >= 2:
            candidate = (index, end)
            if not any(not (candidate[1] <= left or candidate[0] >= right) for left, right in groups):
                groups.append(candidate)
        index = max(end, index + 1)

    return sorted(groups)


def _render_group(texts: list[str]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "NICOReflowHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=9,
        spaceAfter=5,
        keepWithNext=True,
    )
    body = ParagraphStyle(
        "NICOReflowBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
        spaceAfter=3,
    )
    bullet = ParagraphStyle(
        "NICOReflowBullet",
        parent=body,
        leftIndent=12,
        firstLineIndent=-8,
    )
    eyebrow = ParagraphStyle(
        "NICOReflowEyebrow",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=7.4,
        leading=9,
        textColor=colors.HexColor("#b45309"),
        spaceAfter=4,
    )

    story: list[Any] = []
    for page_index, text in enumerate(texts):
        lines = _content_lines(text)
        if not lines:
            continue
        title = lines[0] if _ordinary_sparse_stage(text) else ""
        if page_index:
            story.append(Spacer(1, 0.08 * inch))
        for line_index, line in enumerate(lines):
            escaped = html.escape(line)
            if title and line_index == 0:
                story.append(Paragraph(escaped, heading))
            elif "AUTOMATED DRAFT" in line.upper() or "PENDING HUMAN APPROVAL" in line.upper():
                story.append(Paragraph(escaped, eyebrow))
            elif line.startswith(("-", "•")):
                # Keep the literal source prefix. The preservation gate intentionally
                # compares exact extracted report text; changing '-' to '•' made valid
                # sparse groups fail closed and left production reports at 44 pages.
                story.append(Paragraph(escaped, bullet))
            else:
                story.append(Paragraph(escaped, body))

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.58 * inch,
        rightMargin=0.58 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.58 * inch,
        title="NICO Comprehensive compact report sections",
        author="NICO",
        invariant=1,
    )
    document.build(story)
    return buffer.getvalue()


def _preserves_text(original_texts: list[str], replacement_pdf: bytes) -> bool:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(replacement_pdf))
    replacement = _normal(" ".join(_page_text(page) for page in reader.pages)).casefold()
    for text in original_texts:
        for line in _content_lines(text):
            normalized = _normal(line).casefold()
            if len(normalized) < 3:
                continue
            if normalized not in replacement:
                return False
    return True


def compact_sparse_stage_pages(pdf_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    """Reflow only sparse ordinary report pages, preserving all meaningful text.

    The function is deliberately post-render and presentation-only. It never mutates
    canonical JSON, scores, findings, review state, or delivery authority. Groups are
    skipped unless the replacement uses fewer physical pages and every meaningful source
    line is still extractable from the replacement PDF.
    """

    from pypdf import PdfReader, PdfWriter

    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Comprehensive PDF reflow requires valid PDF bytes")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    texts = [_page_text(page) for page in reader.pages]
    replacements: dict[int, tuple[int, bytes]] = {}

    for start, end in _groups(texts):
        original_texts = texts[start:end]
        replacement = _render_group(original_texts)
        replacement_reader = PdfReader(io.BytesIO(replacement))
        if len(replacement_reader.pages) >= end - start:
            continue
        if not _preserves_text(original_texts, replacement):
            continue
        replacements[start] = (end, replacement)

    if not replacements:
        return pdf_bytes, {
            "artifact_schema": VERSION,
            "status": "unchanged",
            "original_pages": len(reader.pages),
            "final_pages": len(reader.pages),
            "compacted_groups": 0,
            "pages_removed": 0,
            "truth_preserved": True,
            "canonical_truth_mutated": False,
        }

    writer = PdfWriter()
    index = 0
    while index < len(reader.pages):
        replacement = replacements.get(index)
        if replacement is None:
            writer.add_page(reader.pages[index])
            index += 1
            continue
        end, replacement_bytes = replacement
        for page in PdfReader(io.BytesIO(replacement_bytes)).pages:
            writer.add_page(page)
        index = end

    output = io.BytesIO()
    writer.write(output)
    final_bytes = output.getvalue()
    final_pages = len(PdfReader(io.BytesIO(final_bytes)).pages)
    return final_bytes, {
        "artifact_schema": VERSION,
        "status": "compacted",
        "original_pages": len(reader.pages),
        "final_pages": final_pages,
        "compacted_groups": len(replacements),
        "pages_removed": len(reader.pages) - final_pages,
        "truth_preserved": True,
        "canonical_truth_mutated": False,
    }


__all__ = ["VERSION", "compact_sparse_stage_pages"]
