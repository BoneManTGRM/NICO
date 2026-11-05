"""Frozen review-only PDF bundles. No approval or renderer side effects.

Inputs are already validated, client-facing section PDFs in canonical order.
Pages are copied without scaling or re-rendering. The caller owns semantic
selection, finality/source validation, and persistent atomic publication.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import time
import zipfile
from collections.abc import Mapping, Sequence
from typing import Any

from pypdf import PdfReader, PdfWriter

SCHEMA = "nico.ordinary-review-bundle.v2"
MAX_VOLUME_PAGES = 60
MAX_SOURCE_PAGES = 480
MAX_TOTAL_PAGES = 512
MAX_VOLUMES = 16
MAX_SECTIONS = 128
MAX_BYTES = 4 * 1024 * 1024
MAX_SECONDS = 60
ROWS_PER_INDEX_PAGE = 24
_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_IDENTITY_KEYS = {"run_id", "repository", "commit_sha", "report_language", "canonical_truth_sha256"}


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _IDENTITY_KEYS:
        raise ValueError("bundle_identity_fields")
    result = dict(value)
    if any(not isinstance(item, str) or not item or len(item) > 200 for item in result.values()):
        raise ValueError("bundle_identity_value")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", result["run_id"]):
        raise ValueError("bundle_run_id")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", result["repository"]):
        raise ValueError("bundle_repository")
    if not re.fullmatch(r"[0-9a-f]{40}", result["commit_sha"]) or not _SHA.fullmatch(result["canonical_truth_sha256"]):
        raise ValueError("bundle_source_digest")
    if result["report_language"] not in {"en", "es-MX"}:
        raise ValueError("bundle_locale")
    return result


def _tick(start: float) -> None:
    # Cooperative deadline between bounded parsing/copying steps. A caller must
    # use a worker deadline for hard preemption of a single library operation.
    if time.monotonic() - start > MAX_SECONDS:
        raise ValueError("bundle_time_limit")


def _reader(data: bytes) -> PdfReader:
    if not isinstance(data, bytes) or not data.startswith(b"%PDF") or len(data) > MAX_BYTES:
        raise ValueError("bundle_pdf_input")
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted or len(reader.pages) < 1:
        raise ValueError("bundle_pdf_population")
    if len(reader.pages) > MAX_SOURCE_PAGES:
        raise ValueError("bundle_page_limit")
    return reader


def _page_digest(page: Any) -> str:
    """Coverage proof, additional to the authoritative whole-file hash."""
    contents = page.get_contents()
    return _sha(_json({
        "stream": _sha(contents.get_data() if contents is not None else b""),
        "text": page.extract_text() or "",
        "media": [str(n) for n in page.mediabox],
        "crop": [str(n) for n in page.cropbox],
        "rotation": page.get("/Rotate", 0),
    }))


def _index_pages(segment_count: int) -> int:
    return (segment_count + ROWS_PER_INDEX_PAGE - 1) // ROWS_PER_INDEX_PAGE


def _plan(inventory: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    volumes: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    used = 0
    for section in inventory:
        if set(section) != {"section_id", "sha256", "size_bytes", "page_count", "page_digests"}:
            raise ValueError("bundle_source_fields")
        offset = 0
        count = section["page_count"]
        while offset < count:
            available = MAX_VOLUME_PAGES - _index_pages(len(current) + 1) - used
            # Preserve an entire section where it fits in a fresh volume.
            if current and (available <= 0 or (offset == 0 and count <= MAX_VOLUME_PAGES - 1 and count > available)):
                volumes.append(current)
                current, used = [], 0
                continue
            take = min(count - offset, available)
            current.append({"section_id": section["section_id"], "source_start": offset, "page_count": take})
            used += take
            offset += take
            if offset < count:
                volumes.append(current)
                current, used = [], 0
    if current:
        volumes.append(current)
    if len(volumes) > MAX_VOLUMES:
        raise ValueError("bundle_volume_limit")
    return volumes


def _navigation(segments: list[dict[str, Any]], number: int, total: int, identity: Mapping[str, str]) -> bytes:
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.pagesizes import letter

    spanish = identity["report_language"] == "es-MX"
    output = io.BytesIO()
    canvas = Canvas(output, pagesize=letter, invariant=1)
    for first in range(0, len(segments), ROWS_PER_INDEX_PAGE):
        canvas.setFont("Helvetica-Bold", 14)
        label = "Informe principal" if spanish else "Main report"
        if number != 1:
            label = "Apéndice" if spanish else "Appendix"
        canvas.drawString(42, 750, f"{label} — {'Volumen' if spanish else 'Volume'} {number} / {total}")
        canvas.setFont("Helvetica", 9)
        canvas.drawString(42, 724, "BORRADOR AUTOMATIZADO | ENTREGA BLOQUEADA" if spanish else "AUTOMATED DRAFT | CLIENT DELIVERY BLOCKED")
        canvas.drawString(42, 704, "Revisar el conjunto completo; este volumen no autoriza la entrega." if spanish else "Review the complete bundle; this volume does not authorize delivery.")
        canvas.drawString(42, 684, f"SHA: {identity['commit_sha']}")
        canvas.drawString(42, 664, f"Locale: {identity['report_language']}")
        for row, segment in enumerate(segments[first:first + ROWS_PER_INDEX_PAGE]):
            start = segment["volume_start"] + 1
            end = start + segment["page_count"] - 1
            suffix = " (cont.)" if segment["source_start"] else ""
            canvas.drawString(42, 630 - row * 20, segment["section_id"] + suffix)
            canvas.drawRightString(570, 630 - row * 20, f"{start}–{end}")
        canvas.showPage()
    canvas.save()
    return output.getvalue()


def build_review_bundle(identity: Mapping[str, Any], sections: Sequence[tuple[str, bytes]]) -> dict[str, Any]:
    """Return all bytes together only after complete deterministic validation."""
    started = time.monotonic()
    identity = _identity(identity)
    if not 1 <= len(sections) <= MAX_SECTIONS:
        raise ValueError("bundle_section_limit")
    inventory, readers = [], {}
    size = pages = 0
    for section_id, data in sections:
        _tick(started)
        if not isinstance(section_id, str) or not _ID.fullmatch(section_id) or section_id in readers:
            raise ValueError("bundle_section_identity")
        if not isinstance(data, bytes):
            raise ValueError("bundle_pdf_input")
        size += len(data)
        if size > MAX_BYTES:
            raise ValueError("bundle_byte_limit")
        reader = _reader(data)
        pages += len(reader.pages)
        if pages > MAX_SOURCE_PAGES:
            raise ValueError("bundle_page_limit")
        readers[section_id] = reader
        inventory.append({"section_id": section_id, "sha256": _sha(data), "size_bytes": len(data),
                          "page_count": len(reader.pages), "page_digests": [_page_digest(p) for p in reader.pages]})
    plan = _plan(inventory)
    members, files = [], []
    size = 0
    for number, segments in enumerate(plan, 1):
        _tick(started)
        index_count = _index_pages(len(segments))
        position = index_count
        for segment in segments:
            segment["volume_start"] = position
            position += segment["page_count"]
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(_navigation(segments, number, len(plan), identity))), import_outline=False)
        for segment in segments:
            reader = readers[segment["section_id"]]
            for index in range(segment["source_start"], segment["source_start"] + segment["page_count"]):
                writer.add_page(reader.pages[index])
            writer.add_outline_item(segment["section_id"], segment["volume_start"])
        writer.set_page_label(0, len(writer.pages) - 1, style="/D", start=1)
        output = io.BytesIO()
        writer.write(output)
        data = output.getvalue()
        size += len(data)
        if size > MAX_BYTES:
            raise ValueError("bundle_byte_limit")
        filename = f"volume-{number:03d}-{identity['report_language']}.pdf"
        members.append({"filename": filename, "volume": number, "role": "main" if number == 1 else "appendix",
                        "sha256": _sha(data), "size_bytes": len(data), "page_count": len(writer.pages),
                        "index_pages": index_count, "segments": segments})
        files.append({"filename": filename, "pdf_base64": base64.b64encode(data).decode("ascii")})
    manifest = {"artifact_schema": SCHEMA, "identity": identity, "approval_status": "pending_human_approval",
                "client_delivery_allowed": False, "source_sections": inventory, "volumes": members,
                "source_page_count": pages, "total_page_count": sum(v["page_count"] for v in members)}
    result = {"manifest": manifest, "manifest_sha256": _sha(_json(manifest)), "files": files}
    validate_review_bundle(result, expected_identity=identity, expected_manifest_sha256=result["manifest_sha256"])
    _tick(started)
    return result


def validate_review_bundle(bundle: Mapping[str, Any], *, expected_identity: Mapping[str, Any], expected_manifest_sha256: str) -> None:
    """Require a digest from the retained review identity, never from the request."""
    started = time.monotonic()
    identity = _identity(expected_identity)
    if set(bundle) != {"manifest", "manifest_sha256", "files"}:
        raise ValueError("bundle_fields")
    manifest = bundle["manifest"]
    if not isinstance(manifest, Mapping) or set(manifest) != {
        "artifact_schema", "identity", "approval_status", "client_delivery_allowed",
        "source_sections", "volumes", "source_page_count", "total_page_count",
    }:
        raise ValueError("bundle_manifest_fields")
    if not isinstance(expected_manifest_sha256, str) or not _SHA.fullmatch(expected_manifest_sha256):
        raise ValueError("bundle_manifest_digest")
    if bundle["manifest_sha256"] != expected_manifest_sha256 or _sha(_json(manifest)) != expected_manifest_sha256:
        raise ValueError("bundle_manifest_digest")
    if manifest["artifact_schema"] != SCHEMA or manifest["identity"] != identity:
        raise ValueError("bundle_identity_mismatch")
    if manifest["client_delivery_allowed"] is not False or manifest["approval_status"] != "pending_human_approval":
        raise ValueError("bundle_review_only")
    inventory, members, files = manifest["source_sections"], manifest["volumes"], bundle["files"]
    if not 1 <= len(inventory) <= MAX_SECTIONS or not 1 <= len(members) <= MAX_VOLUMES or len(files) != len(members):
        raise ValueError("bundle_population")
    expected_pages = []
    source_bytes = 0
    ids = set()
    for section in inventory:
        if set(section) != {"section_id", "sha256", "size_bytes", "page_count", "page_digests"}:
            raise ValueError("bundle_source_fields")
        section_id = section["section_id"]
        count = section["page_count"]
        if not isinstance(section_id, str) or not _ID.fullmatch(section_id) or section_id in ids:
            raise ValueError("bundle_section_identity")
        ids.add(section_id)
        if type(count) is not int or not 1 <= count <= MAX_SOURCE_PAGES or len(section["page_digests"]) != count:
            raise ValueError("bundle_source_population")
        if not _SHA.fullmatch(section["sha256"]) or type(section["size_bytes"]) is not int or section["size_bytes"] <= 0:
            raise ValueError("bundle_source_digest")
        source_bytes += section["size_bytes"]
        expected_pages.extend((section_id, n, digest) for n, digest in enumerate(section["page_digests"]))
    if len(expected_pages) > MAX_SOURCE_PAGES or source_bytes > MAX_BYTES or manifest["source_page_count"] != len(expected_pages):
        raise ValueError("bundle_source_limit")
    observed_pages = []
    size = total_pages = 0
    for number, (member, file) in enumerate(zip(members, files, strict=True), 1):
        _tick(started)
        if set(member) != {"filename", "volume", "role", "sha256", "size_bytes", "page_count", "index_pages", "segments"} or set(file) != {"filename", "pdf_base64"}:
            raise ValueError("bundle_member_fields")
        filename = f"volume-{number:03d}-{identity['report_language']}.pdf"
        if member["filename"] != filename or file["filename"] != filename or member["volume"] != number:
            raise ValueError("bundle_member_order")
        if member["role"] != ("main" if number == 1 else "appendix"):
            raise ValueError("bundle_member_role")
        encoded = file["pdf_base64"]
        if not isinstance(encoded, str) or len(encoded) > ((MAX_BYTES + 2) // 3) * 4:
            raise ValueError("bundle_byte_limit")
        data = base64.b64decode(encoded, validate=True)
        size += len(data)
        if size > MAX_BYTES:
            raise ValueError("bundle_byte_limit")
        if _sha(data) != member["sha256"] or len(data) != member["size_bytes"]:
            raise ValueError("bundle_member_digest")
        reader = _reader(data)
        if len(reader.pages) != member["page_count"] or len(reader.pages) > MAX_VOLUME_PAGES:
            raise ValueError("bundle_volume_page_limit")
        total_pages += len(reader.pages)
        if total_pages > MAX_TOTAL_PAGES:
            raise ValueError("bundle_total_page_limit")
        segments = member["segments"]
        if not segments or member["index_pages"] != _index_pages(len(segments)):
            raise ValueError("bundle_index_population")
        position = member["index_pages"]
        for segment in segments:
            if set(segment) != {"section_id", "source_start", "page_count", "volume_start"}:
                raise ValueError("bundle_segment_fields")
            count = segment["page_count"]
            start = segment["source_start"]
            if type(count) is not int or count <= 0 or type(start) is not int or start < 0 or segment["volume_start"] != position:
                raise ValueError("bundle_segment_range")
            if position + count > len(reader.pages):
                raise ValueError("bundle_segment_range")
            for offset in range(count):
                observed_pages.append((segment["section_id"], start + offset, _page_digest(reader.pages[position + offset])))
            position += count
        if position != len(reader.pages):
            raise ValueError("bundle_unaccounted_pages")
        expected_navigation = PdfReader(io.BytesIO(_navigation(segments, number, len(members), identity)))
        if (len(expected_navigation.pages) != member["index_pages"]
                or [_page_digest(p) for p in expected_navigation.pages] != [_page_digest(p) for p in reader.pages[:member["index_pages"]]]
                or reader.page_labels != [str(n) for n in range(1, len(reader.pages) + 1)]
                or [(item.title, reader.get_destination_page_number(item)) for item in reader.outline]
                != [(s["section_id"], s["volume_start"]) for s in segments]):
            raise ValueError("bundle_navigation")
    if total_pages != manifest["total_page_count"] or observed_pages != expected_pages:
        raise ValueError("bundle_coverage")
    _tick(started)


def review_bundle_zip(bundle: Mapping[str, Any], *, expected_identity: Mapping[str, Any], expected_manifest_sha256: str) -> bytes:
    validate_review_bundle(bundle, expected_identity=expected_identity, expected_manifest_sha256=expected_manifest_sha256)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        entries = {"bundle-manifest.json": _json(bundle["manifest"])}
        entries.update({f["filename"]: base64.b64decode(f["pdf_base64"], validate=True) for f in bundle["files"]})
        for filename, data in sorted(entries.items()):
            info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            info.create_system = 3
            archive.writestr(info, data)
    return output.getvalue()
