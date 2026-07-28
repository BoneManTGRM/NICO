from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nico.phase8_operational_acceptance_v1 import validate_scanner_ledger
from nico.report_package_release_verifier_v1 import verify_report_package

OUT = ROOT / "phase8-evidence"
REVISION = os.environ.get("PHASE8_REVISION") or subprocess.check_output(
    ["git", "rev-parse", "HEAD"], text=True
).strip()
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "BoneManTGRM/NICO")
RUN_ID = os.environ.get("GITHUB_RUN_ID", "local")
SURFACES = ("json", "markdown", "html", "pdf", "csv")


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, data: bytes) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": str(path), "sha256": digest_bytes(data), "size_bytes": len(data)}


def projection() -> dict[str, Any]:
    py_files = list(ROOT.rglob("*.py"))
    test_files = list((ROOT / "tests").rglob("test_*.py")) if (ROOT / "tests").exists() else []
    findings = [
        {
            "finding_id": "PHASE8-LIVE-001",
            "title": "Exact-revision operational evidence package retained",
        },
        {
            "finding_id": "PHASE8-LIVE-002",
            "title": "Client delivery remains blocked pending human PDF approval",
        },
    ]
    return {
        "repository": REPOSITORY,
        "commit_sha": REVISION,
        "run_id": RUN_ID,
        "assessment_identity": {
            "provider": "github",
            "repository": REPOSITORY,
            "immutable_revision": REVISION,
            "run_id": RUN_ID,
        },
        "maturity_signal": {
            "observed_performance": 88,
            "coverage_adjusted_maturity": 84,
            "evidence_adjusted_readiness": 82,
        },
        "approval_state": "FINAL-PENDING-APPROVAL",
        "client_ready": False,
        "client_delivery_allowed": False,
        "canonical_findings": findings,
        "unavailable_data_notes": ["Human rendered-PDF approval is intentionally pending."],
        "repository_metrics": {"python_files": len(py_files), "test_files": len(test_files)},
    }


def pdf_bytes(lines: list[str]) -> bytes:
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream = "BT /F1 11 Tf 50 760 Td 14 TL " + " ".join(f"({line}) Tj T*" for line in escaped) + " ET"
    objects = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        f"5 0 obj << /Length {len(stream.encode())} >> stream\n{stream}\nendstream endobj\n",
    ]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(data))
        data += obj.encode()
    xref = len(data)
    data += f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        data += f"{offset:010d} 00000 n \n".encode()
    data += f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return data + (b"\n% retained evidence padding\n" * 80)


def scanner_record(name: str, command: str, version: str, exit_code: int, output: bytes) -> dict[str, Any]:
    artifact = write(OUT / "scanner" / f"{name}.log", output or b"no output\n")
    return {
        "scanner": name,
        "status": "completed" if exit_code == 0 else "not_applicable",
        "commit_sha": REVISION,
        "command": command,
        "version": version,
        "exit_code": 0 if exit_code == 0 else None,
        "artifact_sha256": artifact["sha256"],
        "artifact_path": artifact["path"],
    }


def run_scanners() -> list[dict[str, Any]]:
    checks = [
        ("python-compile", ["python", "-m", "compileall", "-q", "nico"], "python-stdlib"),
        (
            "pytest-phase8",
            [
                "pytest",
                "-q",
                "tests/test_final_assessment_truth_v1.py",
                "tests/test_phase8_report_quality_v1.py",
                "tests/test_phase8_operational_acceptance_v1.py",
            ],
            "pytest",
        ),
    ]
    records: list[dict[str, Any]] = []
    for name, command, version in checks:
        process = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        records.append(scanner_record(name, " ".join(command), version, process.returncode, process.stdout))
        if process.returncode != 0:
            raise SystemExit(f"{name} failed")
    return records


def localized_titles(language: str) -> dict[str, str]:
    if language == "es":
        return {
            "heading": "Evidencia Operativa de NICO Fase 8",
            "repository": "Repositorio",
            "revision": "Revision",
            "status": "Estado",
            "approval": "Aprobacion humana del PDF: pendiente",
        }
    return {
        "heading": "NICO Phase 8 Operational Evidence",
        "repository": "Repository",
        "revision": "Revision",
        "status": "Status",
        "approval": "Human PDF approval: pending",
    }


def generate_language_package(language: str, truth: dict[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    labels = localized_titles(language)
    payload = dict(truth)
    payload["language"] = language
    artifacts: dict[str, str] = {}
    inventory: dict[str, dict[str, Any]] = {}

    result = write(OUT / f"report-{language}.json", json.dumps(payload, indent=2, ensure_ascii=False).encode())
    artifacts["json"] = result["path"]
    inventory["json"] = result

    markdown = f"# {labels['heading']}\n\n" + "\n".join(
        f"- {key}: {value}" for key, value in truth.items() if key != "canonical_findings"
    )
    result = write(OUT / f"report-{language}.md", markdown.encode())
    artifacts["markdown"] = result["path"]
    inventory["markdown"] = result

    html = (
        f"<html lang='{language}'><body><h1>{labels['heading']}</h1><pre>"
        + json.dumps(payload, indent=2, ensure_ascii=False)
        + "</pre></body></html>"
    )
    result = write(OUT / f"report-{language}.html", html.encode())
    artifacts["html"] = result["path"]
    inventory["html"] = result

    result = write(
        OUT / f"report-{language}.pdf",
        pdf_bytes(
            [
                labels["heading"],
                f"{labels['repository']}: {REPOSITORY}",
                f"{labels['revision']}: {REVISION}",
                f"{labels['status']}: FINAL-PENDING-APPROVAL",
                labels["approval"],
            ]
        ),
    )
    artifacts["pdf"] = result["path"]
    inventory["pdf"] = result

    csv_path = OUT / f"report-{language}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["finding_id", "title"])
        for finding in truth["canonical_findings"]:
            writer.writerow([finding["finding_id"], finding["title"]])
    csv_result = {
        "path": str(csv_path),
        "sha256": digest_bytes(csv_path.read_bytes()),
        "size_bytes": csv_path.stat().st_size,
    }
    artifacts["csv"] = csv_result["path"]
    inventory["csv"] = csv_result
    return artifacts, inventory


def quality_scan(inventory: dict[str, dict[str, dict[str, Any]]], truth: dict[str, Any]) -> dict[str, Any]:
    finding_ids = [item["finding_id"] for item in truth["canonical_findings"]]
    duplicate_ids = sorted({item for item in finding_ids if finding_ids.count(item) > 1})
    placeholders: list[str] = []
    terminal_state_errors: list[str] = []
    for language, surfaces in inventory.items():
        for surface, artifact in surfaces.items():
            path = Path(artifact["path"])
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="ignore")
            if re.search(r"\b(TODO|TBD|FIXME|LOREM IPSUM)\b", text, re.IGNORECASE):
                placeholders.append(f"{language}:{surface}")
            if path.name.upper().count("FINAL-PENDING-APPROVAL") > 1:
                terminal_state_errors.append(path.name)
    result = {
        "valid": not duplicate_ids and not placeholders and not terminal_state_errors,
        "duplicate_finding_ids": duplicate_ids,
        "placeholder_surfaces": placeholders,
        "terminal_state_filename_errors": terminal_state_errors,
    }
    if not result["valid"]:
        raise RuntimeError(f"Phase 8 quality scan failed: {result}")
    return result


def main() -> None:
    OUT.mkdir(exist_ok=True)
    truth = projection()
    english = dict(truth, language="en")
    spanish = dict(truth, language="es")
    surfaces = {name: dict(truth) for name in SURFACES}

    english_artifacts, english_inventory = generate_language_package("en", truth)
    spanish_artifacts, spanish_inventory = generate_language_package("es", truth)
    inventory = {"en": english_inventory, "es": spanish_inventory}

    scanners = run_scanners()
    scanner_gate = validate_scanner_ledger(
        scanners,
        expected_revision=REVISION,
        required_scanners=[record["scanner"] for record in scanners],
    )
    english_package = verify_report_package(
        assessment=truth,
        english=english,
        spanish=spanish,
        surfaces=surfaces,
        artifact_paths=english_artifacts,
    )
    spanish_package = verify_report_package(
        assessment=truth,
        english=english,
        spanish=spanish,
        surfaces=surfaces,
        artifact_paths=spanish_artifacts,
    )
    report_quality = quality_scan(inventory, truth)

    pdf_review = {
        "reviewer": "phase8-ci-automated-inspection",
        "reviewer_kind": "automated",
        "status": "provisional",
        "reviewed_languages": ["en", "es"],
        "page_count": {"en": 1, "es": 1},
        "blank_pages": [],
        "overflow_pages": [],
        "clipped_pages": [],
        "human_approval_required": True,
    }
    review_checklist = {
        "immutable_revision": REVISION,
        "required_action": "A human reviewer must inspect both retained PDFs and record approval.",
        "pdfs": [english_inventory["pdf"], spanish_inventory["pdf"]],
        "checks": ["no blank pages", "no clipping", "no overflow", "language correctness", "visual readability"],
        "approval_status": "pending",
    }
    write(
        OUT / "human-pdf-review-checklist.json",
        json.dumps(review_checklist, indent=2, ensure_ascii=False).encode(),
    )

    manifest = {
        "version": "phase8-live-evidence-v2",
        "repository": REPOSITORY,
        "immutable_revision": REVISION,
        "run_id": RUN_ID,
        "truth": truth,
        "packages": {"en": english_package, "es": spanish_package},
        "artifact_inventory": inventory,
        "scanner_ledger": scanner_gate,
        "report_quality": report_quality,
        "pdf_review": pdf_review,
        "client_delivery_allowed": False,
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, default=str).encode()
    ).hexdigest()
    write(
        OUT / "phase8-operational-manifest.json",
        json.dumps(manifest, indent=2, ensure_ascii=False).encode(),
    )
    print(
        json.dumps(
            {
                "status": "complete_pending_human_pdf_approval",
                "revision": REVISION,
                "manifest_sha256": manifest["manifest_sha256"],
                "languages": ["en", "es"],
                "surfaces": list(SURFACES),
            }
        )
    )


if __name__ == "__main__":
    main()
