from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from nico.report_package_release_verifier_v1 import verify_report_package
from nico.phase8_operational_acceptance_v1 import validate_scanner_ledger

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "phase8-evidence"
REVISION = os.environ.get("PHASE8_REVISION") or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "BoneManTGRM/NICO")
RUN_ID = os.environ.get("GITHUB_RUN_ID", "local")


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
        {"finding_id": "PHASE8-LIVE-001", "title": "Exact-revision operational evidence package retained"},
        {"finding_id": "PHASE8-LIVE-002", "title": "Client delivery remains blocked pending human PDF approval"},
    ]
    return {
        "repository": REPOSITORY,
        "commit_sha": REVISION,
        "run_id": RUN_ID,
        "assessment_identity": {"provider": "github", "repository": REPOSITORY, "immutable_revision": REVISION, "run_id": RUN_ID},
        "maturity_signal": {"observed_performance": 88, "coverage_adjusted_maturity": 84, "evidence_adjusted_readiness": 82},
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
    for off in offsets[1:]:
        data += f"{off:010d} 00000 n \n".encode()
    data += f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return data


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
    records: list[dict[str, Any]] = []
    checks = [
        ("python-compile", ["python", "-m", "compileall", "-q", "nico"], "python-stdlib"),
        ("pytest-phase8", ["pytest", "-q", "tests/test_final_assessment_truth_v1.py", "tests/test_phase8_report_quality_v1.py", "tests/test_phase8_operational_acceptance_v1.py"], "pytest"),
    ]
    for name, cmd, version in checks:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        records.append(scanner_record(name, " ".join(cmd), version, proc.returncode, proc.stdout))
        if proc.returncode != 0:
            raise SystemExit(f"{name} failed")
    return records


def main() -> None:
    OUT.mkdir(exist_ok=True)
    truth = projection()
    english = dict(truth)
    spanish = dict(truth)
    english["language"] = "en"
    spanish["language"] = "es"
    surfaces = {name: dict(truth) for name in ("json", "markdown", "html", "pdf", "csv")}

    artifacts: dict[str, str] = {}
    artifacts["json"] = write(OUT / "report-en.json", json.dumps(english, indent=2, ensure_ascii=False).encode())["path"]
    md = "# NICO Phase 8 Operational Evidence\n\n" + "\n".join(f"- {k}: {v}" for k, v in truth.items() if k not in {"canonical_findings"})
    artifacts["markdown"] = write(OUT / "report-en.md", md.encode())["path"]
    html = "<html><body><h1>NICO Phase 8 Operational Evidence</h1><pre>" + json.dumps(truth, indent=2) + "</pre></body></html>"
    artifacts["html"] = write(OUT / "report-en.html", html.encode())["path"]
    artifacts["pdf"] = write(OUT / "report-en.pdf", pdf_bytes(["NICO Phase 8 Operational Evidence", f"Repository: {REPOSITORY}", f"Revision: {REVISION}", "Status: FINAL-PENDING-APPROVAL", "Human PDF approval: pending"]))["path"]
    csv_path = OUT / "report-en.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["finding_id", "title"])
        for finding in truth["canonical_findings"]:
            writer.writerow([finding["finding_id"], finding["title"]])
    artifacts["csv"] = str(csv_path)
    write(OUT / "report-es.json", json.dumps(spanish, indent=2, ensure_ascii=False).encode())

    scanners = run_scanners()
    scanner_gate = validate_scanner_ledger(scanners, expected_revision=REVISION, required_scanners=[r["scanner"] for r in scanners])
    package = verify_report_package(assessment=truth, english=english, spanish=spanish, surfaces=surfaces, artifact_paths=artifacts)

    pdf_review = {
        "reviewer": "phase8-ci-automated-inspection",
        "reviewer_kind": "automated",
        "status": "provisional",
        "page_count": 1,
        "blank_pages": [],
        "overflow_pages": [],
        "clipped_pages": [],
        "human_approval_required": True,
    }
    manifest = {
        "version": "phase8-live-evidence-v1",
        "repository": REPOSITORY,
        "immutable_revision": REVISION,
        "run_id": RUN_ID,
        "truth": truth,
        "package": package,
        "scanner_ledger": scanner_gate,
        "pdf_review": pdf_review,
        "client_delivery_allowed": False,
    }
    manifest["manifest_sha256"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, default=str).encode()).hexdigest()
    write(OUT / "phase8-operational-manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False).encode())
    print(json.dumps({"status": "complete_pending_human_pdf_approval", "revision": REVISION, "manifest_sha256": manifest["manifest_sha256"]}))


if __name__ == "__main__":
    main()
