from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from nico.report_surface_truth_v1 import validate_localizations, validate_report_surfaces

VERSION = "nico.report_package_release_verifier.v1"


@dataclass(frozen=True)
class ReportArtifact:
    surface: str
    path: str
    sha256: str
    size_bytes: int


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_report_package(
    *,
    assessment: Mapping,
    english: Mapping,
    spanish: Mapping,
    surfaces: Mapping[str, Mapping],
    artifact_paths: Mapping[str, str],
    required_surfaces: Sequence[str] = ("json", "markdown", "html", "pdf", "csv"),
) -> dict:
    surface_result = validate_report_surfaces(
        assessment,
        surfaces,
        required_surfaces=required_surfaces,
    )
    localization_result = validate_localizations(english, spanish)

    missing_files = []
    artifacts: list[ReportArtifact] = []
    for surface in required_surfaces:
        raw_path = artifact_paths.get(surface)
        if not raw_path:
            missing_files.append(surface)
            continue
        path = Path(raw_path)
        if not path.is_file() or path.stat().st_size <= 0:
            missing_files.append(surface)
            continue
        artifacts.append(
            ReportArtifact(
                surface=surface,
                path=str(path),
                sha256=_hash_file(path),
                size_bytes=path.stat().st_size,
            )
        )

    if missing_files:
        raise RuntimeError(f"Report package incomplete: missing_or_empty={sorted(missing_files)}")

    pdf = next(item for item in artifacts if item.surface == "pdf")
    if pdf.size_bytes < 1024:
        raise RuntimeError("Rendered PDF is too small to be considered a reviewable report")

    return {
        "version": VERSION,
        "valid": True,
        "truth_digest": surface_result["truth_digest"],
        "localization_truth_digest": localization_result["truth_digest"],
        "artifacts": [item.__dict__ for item in artifacts],
        "pdf_visual_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["ReportArtifact", "verify_report_package"]
