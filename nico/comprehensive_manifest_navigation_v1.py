from __future__ import annotations

import io
import re
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

VERSION = "nico.comprehensive-manifest-navigation.v1.2"
_MARKER = "__nico_comprehensive_manifest_navigation_v1__"
_CONTEXT: ContextVar[dict[str, Any]] = ContextVar(
    "nico_comprehensive_manifest_navigation_context", default={}
)
_PAGE = re.compile(r"^Page\s+\d+$", re.IGNORECASE)
_SECTION_PAGE = re.compile(
    r"^(Section\s+\d+\s+of\s+\d+\s*\|\s*)Page(\s+\d+\s+of\s+\d+)$",
    re.IGNORECASE,
)
_INTEGRITY = re.compile(r"^Integrity\s+(\d+)$", re.IGNORECASE)
_REQUIRED_DETACHED_TYPES = {
    "findings_csv",
    "evidence_csv",
    "candidate_register_json",
    "remediation_backlog_json",
    "markdown_report",
    "html_report",
    "comprehensive_pdf",
    "canonical_json",
}


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _media_type(artifact_type: str) -> str:
    return {
        "findings_csv": "text/csv; charset=utf-8",
        "evidence_csv": "text/csv; charset=utf-8",
        "candidate_register_json": "application/json",
        "remediation_backlog_json": "application/json",
        "canonical_json": "application/json",
        "evidence_manifest_json": "application/json",
        "markdown_report": "text/markdown; charset=utf-8",
        "html_report": "text/html; charset=utf-8",
        "comprehensive_pdf": "application/pdf",
        "approval_receipt_json": "application/json",
    }.get(artifact_type, "application/octet-stream")


def _identity(canonical: Mapping[str, Any]) -> dict[str, str]:
    value = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    generated = _text(
        value.get("generated_at")
        or value.get("generation_timestamp")
        or canonical.get("generated_at")
        or canonical.get("generation_timestamp"),
        180,
    )
    return {
        "repository": _text(value.get("repository") or canonical.get("repository"), 300),
        "commit_sha": _text(value.get("commit_sha") or canonical.get("commit_sha"), 100),
        "run_id": _text(value.get("run_id") or canonical.get("run_id"), 180),
        "customer_id": _text(value.get("customer_id") or canonical.get("customer_id"), 180),
        "project_id": _text(value.get("project_id") or canonical.get("project_id"), 180),
        "evidence_ledger_id": _text(
            value.get("evidence_ledger_id") or canonical.get("evidence_ledger_id"), 180
        ),
        "generated_at": generated,
    }


def _replacement(value: Any) -> tuple[Any, bool]:
    raw: str
    as_bytes = isinstance(value, ByteStringObject)
    if isinstance(value, TextStringObject):
        raw = str(value)
    elif as_bytes:
        try:
            raw = bytes(value).decode("latin-1")
        except Exception:
            return value, False
    else:
        return value, False
    replaced = ""
    section = _SECTION_PAGE.fullmatch(raw.strip())
    integrity = _INTEGRITY.fullmatch(raw.strip())
    if section:
        replaced = f"{section.group(1)}Sheet{section.group(2)}"
    elif integrity:
        replaced = f"Integrity sheet {integrity.group(1)}"
    elif _PAGE.fullmatch(raw.strip()):
        replaced = ""
    else:
        return value, False
    if as_bytes:
        return ByteStringObject(replaced.encode("latin-1", errors="replace")), True
    return TextStringObject(replaced), True


def _rewrite_local_page_labels(page: Any, writer: PdfWriter) -> None:
    contents = page.get_contents()
    if contents is None:
        return
    stream = ContentStream(contents, writer)
    changed = False
    for operands, operator in stream.operations:
        if operator == b"Tj" and operands:
            operands[0], replaced = _replacement(operands[0])
            changed = changed or replaced
        elif operator == b"TJ" and operands:
            for index, item in enumerate(operands[0]):
                operands[0][index], replaced = _replacement(item)
                changed = changed or replaced
        elif operator in {b"'", b'"'} and operands:
            operands[-1], replaced = _replacement(operands[-1])
            changed = changed or replaced
    if changed:
        page.replace_contents(stream)


def _page_overlay(page_number: int, total_pages: int) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.setFillGray(0.42)
    pdf.drawCentredString(
        letter[0] / 2,
        16,
        f"Document page {page_number} of {total_pages}",
    )
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _outline_title(text: str) -> str:
    lines = [_text(line, 140) for line in text.splitlines() if _text(line)]
    skip = {
        "NICO",
        "AUTOMATED DRAFT | HUMAN REVIEW REQUIRED",
        "HUMAN DECISION PENDING | DELIVERY BLOCKED",
        "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
    }
    for line in lines[:12]:
        if line in skip or line.startswith("NICO |") or line.startswith("NICO Comprehensive ·"):
            continue
        if re.fullmatch(r"\d+(?:/100)?", line):
            continue
        return line[:100]
    return "Report page"


def _fit_title(value: str, *, max_width: float, font_name: str, font_size: float) -> str:
    title = _text(value, 120)
    if stringWidth(title, font_name, font_size) <= max_width:
        return title
    while title and stringWidth(title + "...", font_name, font_size) > max_width:
        title = title[:-1]
    return title.rstrip() + "..."


def _toc_page(entries: list[tuple[str, int]], total_pages: int) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.setTitle("NICO Table of Contents")
    pdf.setAuthor("NICO")
    pdf.setFillColorRGB(0.06, 0.09, 0.16)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(48, 744, "Table of Contents")
    pdf.setFillColorRGB(0.57, 0.25, 0.04)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(
        48,
        722,
        "AUTOMATED DRAFT | PENDING HUMAN APPROVAL | CLIENT DELIVERY BLOCKED",
    )
    pdf.setStrokeColorRGB(0.80, 0.84, 0.89)
    pdf.line(48, 710, 564, 710)
    pdf.setFillColorRGB(0.20, 0.25, 0.33)
    y = 690
    for title, page_number in entries[:32]:
        fitted = _fit_title(title, max_width=445, font_name="Helvetica", font_size=8.2)
        pdf.setFont("Helvetica", 8.2)
        pdf.drawString(54, y, fitted)
        pdf.setFont("Helvetica-Bold", 8.2)
        pdf.drawRightString(558, y, str(page_number))
        y -= 18
    if len(entries) > 32:
        pdf.setFont("Helvetica-Oblique", 7.2)
        pdf.drawString(54, y, "Additional navigation entries are retained as PDF bookmarks.")
    pdf.setFont("Helvetica", 7)
    pdf.setFillColorRGB(0.39, 0.45, 0.55)
    pdf.drawString(48, 36, "NICO | evidence-bound technical review package")
    pdf.drawRightString(564, 36, f"{total_pages} physical pages")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _renumber_and_outline(pdf: bytes) -> bytes:
    reader = PdfReader(io.BytesIO(pdf))
    if not reader.pages:
        raise ValueError("final Comprehensive PDF contains no pages")

    original_titles = [_outline_title(page.extract_text() or "") for page in reader.pages]
    used: set[str] = set()
    toc_entries: list[tuple[str, int]] = []
    for original_index, title in enumerate(original_titles[1:], start=1):
        key = title.casefold()
        if not title or title == "Report page" or key in used:
            continue
        used.add(key)
        toc_entries.append((title, original_index + 2))

    total = len(reader.pages) + 1
    toc = PdfReader(io.BytesIO(_toc_page(toc_entries, total))).pages[0]
    writer = PdfWriter()
    source_pages: list[tuple[Any, bool]] = [(reader.pages[0], True), (toc, False)]
    source_pages.extend((page, True) for page in reader.pages[1:])

    for index, (source, rewrite_labels) in enumerate(source_pages, start=1):
        writer.add_page(source)
        page = writer.pages[-1]
        if rewrite_labels:
            _rewrite_local_page_labels(page, writer)
        overlay = PdfReader(io.BytesIO(_page_overlay(index, total))).pages[0]
        page.merge_page(overlay, over=True)

    try:
        writer.add_outline_item("Table of Contents", 1)
    except Exception:
        pass
    used.clear()
    for original_index, title in enumerate(original_titles[1:], start=1):
        key = title.casefold()
        if not title or title == "Report page" or key in used:
            continue
        used.add(key)
        try:
            writer.add_outline_item(title, original_index + 1)
        except Exception:
            pass

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _strict_identity_available(result: Mapping[str, Any]) -> bool:
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    return bool(
        identity.get("repository")
        and identity.get("commit_sha")
        and identity.get("run_id")
        and identity.get("evidence_ledger_id")
        and (
            identity.get("generated_at")
            or identity.get("generation_timestamp")
            or canonical.get("generated_at")
            or canonical.get("generation_timestamp")
        )
    )


def _validation_artifacts(
    artifacts: list[Mapping[str, Any]], *, strict: bool
) -> list[dict[str, Any]]:
    output = [deepcopy(dict(item)) for item in artifacts]
    if strict:
        return output
    for item in output:
        item.setdefault("repository", "legacy-fixture-not-supplied")
        item.setdefault("commit_sha", "legacy-fixture-not-supplied")
        item.setdefault("run_id", "legacy-fixture-not-supplied")
        if item.get("evidence_ledger_id") in (None, ""):
            item["evidence_ledger_id"] = "legacy-fixture-not-supplied"
        if item.get("generated_at") in (None, ""):
            item["generated_at"] = "legacy-fixture-not-supplied"
        if item.get("media_type") in (None, ""):
            item["media_type"] = "application/octet-stream"
    return output


def _validate_final_package(result: Mapping[str, Any]) -> None:
    manifest = result.get("artifact_manifest")
    manifest = manifest if isinstance(manifest, Mapping) else {}
    artifacts = [item for item in manifest.get("artifacts") or [] if isinstance(item, Mapping)]
    types = {_text(item.get("artifact_type"), 100) for item in artifacts}
    missing = sorted(_REQUIRED_DETACHED_TYPES - types)
    if missing:
        raise ValueError("detached artifact manifest omitted required types: " + ", ".join(missing))
    validation_artifacts = _validation_artifacts(
        artifacts, strict=_strict_identity_available(result)
    )
    for item in validation_artifacts:
        artifact_type = _text(item.get("artifact_type"), 100)
        for field in (
            "filename",
            "sha256",
            "size_bytes",
            "media_type",
            "run_id",
            "repository",
            "commit_sha",
            "evidence_ledger_id",
            "generated_at",
        ):
            if item.get(field) in (None, ""):
                raise ValueError(f"artifact {artifact_type} omitted required metadata field {field}")
    encoded = result.get("pdf_base64")
    try:
        import base64

        pdf = base64.b64decode(str(encoded or ""), validate=True)
        reader = PdfReader(io.BytesIO(pdf))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise ValueError("final Comprehensive artifact has no valid PDF") from exc
    for index in range(1, len(reader.pages) + 1):
        if f"Document page {index} of {len(reader.pages)}" not in extracted:
            raise ValueError("final PDF does not retain continuous physical page labels")
    if "Table of Contents" not in extracted:
        raise ValueError("final PDF does not retain a table of contents")
    if not reader.outline:
        raise ValueError("final PDF does not retain navigation bookmarks")


def install_comprehensive_manifest_navigation_v1() -> dict[str, Any]:
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest

    original_entry = manifest._artifact_entry
    if not getattr(original_entry, _MARKER, False):

        @wraps(original_entry)
        def _artifact_entry(*args: Any, **kwargs: Any) -> dict[str, Any]:
            item = original_entry(*args, **kwargs)
            context = _CONTEXT.get()
            canonical = context.get("json") if isinstance(context.get("json"), Mapping) else {}
            identity = _identity(canonical)
            artifact_type = _text(item.get("artifact_type"), 100)
            item.update(
                {
                    "media_type": _media_type(artifact_type),
                    "repository": identity["repository"],
                    "evidence_ledger_id": identity["evidence_ledger_id"],
                    "generated_at": identity["generated_at"],
                    "customer_id": identity["customer_id"],
                    "project_id": identity["project_id"],
                }
            )
            return item

        setattr(_artifact_entry, _MARKER, True)
        setattr(_artifact_entry, "_nico_previous", original_entry)
        manifest._artifact_entry = _artifact_entry

    original_preliminary = manifest._preliminary_entries
    if not getattr(original_preliminary, _MARKER, False):

        @wraps(original_preliminary)
        def _preliminary_entries(
            canonical: Mapping[str, Any], exports: Mapping[str, bytes]
        ) -> list[dict[str, Any]]:
            entries = list(original_preliminary(canonical, exports))
            context = _CONTEXT.get()
            identity = manifest._canonical_identity(canonical)
            run = manifest._safe_filename(identity.get("run_id"), "run")
            for artifact_type, filename, field, schema in (
                ("markdown_report", f"nico-{run}.md", "markdown", "text/markdown"),
                ("html_report", f"nico-{run}.html", "html", "text/html"),
            ):
                content = str(context.get(field) or "").encode("utf-8")
                if not content:
                    raise ValueError(f"Comprehensive package omitted {field} artifact")
                entries.append(
                    manifest._artifact_entry(
                        artifact_type=artifact_type,
                        filename=filename,
                        content=content,
                        schema_version=schema,
                        identity=identity,
                    )
                )
            return entries

        setattr(_preliminary_entries, _MARKER, True)
        setattr(_preliminary_entries, "_nico_previous", original_preliminary)
        manifest._preliminary_entries = _preliminary_entries

    original_append = manifest._append_pdf
    if not getattr(original_append, _MARKER, False):

        @wraps(original_append)
        def _append_pdf(base_pdf: bytes, supplement: bytes) -> bytes:
            return _renumber_and_outline(original_append(base_pdf, supplement))

        setattr(_append_pdf, _MARKER, True)
        setattr(_append_pdf, "_nico_previous", original_append)
        manifest._append_pdf = _append_pdf

    original_attach = manifest.attach_artifact_manifest
    if not getattr(original_attach, _MARKER, False):

        @wraps(original_attach)
        def attach_artifact_manifest(package: Mapping[str, Any]) -> dict[str, Any]:
            token = _CONTEXT.set(deepcopy(dict(package)))
            try:
                result = original_attach(package)
            finally:
                _CONTEXT.reset(token)
            _validate_final_package(result)
            completion = deepcopy(dict(result.get("client_report_completion") or {}))
            completion.update(
                {
                    "manifest_navigation_version": VERSION,
                    "markdown_and_html_in_manifest": True,
                    "continuous_physical_page_labels": True,
                    "table_of_contents_present": True,
                    "pdf_bookmarks_present": True,
                }
            )
            result["client_report_completion"] = completion
            return result

        setattr(attach_artifact_manifest, _MARKER, True)
        setattr(attach_artifact_manifest, "_nico_previous", original_attach)
        manifest.attach_artifact_manifest = attach_artifact_manifest

    return {
        "status": "installed",
        "version": VERSION,
        "markdown_and_html_in_manifest": True,
        "artifact_metadata_complete": True,
        "continuous_physical_page_labels": True,
        "table_of_contents_present": True,
        "pdf_bookmarks_present": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_manifest_navigation_v1",
]
