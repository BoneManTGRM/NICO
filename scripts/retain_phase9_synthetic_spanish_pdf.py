"""Retain only the verified es-MX synthetic worker PDF and its proof sidecar."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

from pypdf import PdfReader


PROBE = Path("tests/spanish_worker_qualification_probe.py")
OUTPUT = Path("phase9-synthetic-spanish-proof")


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def verify(snapshot, observed):
    manifest = snapshot["manifest"]
    identity = snapshot["canonical"]["identity"]
    if identity["report_language"] != "es-MX":
        raise ValueError("not an es-MX canonical report")
    if (manifest["lifecycle"]["report_finality"] != "automated_draft"
        or manifest["lifecycle"]["client_delivery_status"] != "blocked"
        or manifest["approval"]["decision"] != "pending"
        or manifest["approval"]["client_delivery_allowed"] is not False):
        raise ValueError("not a blocked automated draft")
    rows = [row for row in manifest["artifacts"] if row["artifact_type"] == "comprehensive_pdf"]
    pdf = base64.b64decode(snapshot["artifacts"]["comprehensive_pdf"], validate=True)
    digest = sha256(pdf)
    if (len(rows) != 1 or rows[0]["sha256"] != digest
        or rows[0]["size_bytes"] != len(pdf) or observed["pdf_sha256"] != digest):
        raise ValueError("PDF manifest digest/length mismatch")
    reader = PdfReader(io.BytesIO(pdf), strict=True)
    if not pdf.startswith(b"%PDF-") or not reader.pages or len(reader.pages) != observed["pages"]:
        raise ValueError("PDF signature or page count mismatch")
    return pdf, manifest


def main():
    revision = os.environ["PHASE9_REVISION"]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True)
    if not re.fullmatch(r"[a-f0-9]{40}", revision) or head != revision or dirty:
        raise ValueError("expected exact clean tracked checkout")
    with tempfile.TemporaryDirectory(prefix="nico-phase9-spanish-") as tmp:
        root = Path(tmp)
        from tests.owned_worker_environment import owned_worker_environment

        # Do not forward ambient PYTHONPATH: the exact checkout is the sole source overlay.
        parent = {key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ}
        environment = owned_worker_environment(Path.cwd(), root, parent)
        environment.update({
            "HOME": tmp, "PYTHONHASHSEED": "0",
            "NICO_TEST_WORKER_RICH_FIXTURE": "1", "NICO_TEST_WORKER_EXPORT": str(root),
        })
        run = subprocess.run(
            [sys.executable, str(PROBE)], env=environment, text=True,
            stdout=subprocess.PIPE, check=True, timeout=180,
        )
        marker = "NICO_WORKER_QUALIFICATION="
        observations = [json.loads(line[len(marker):]) for line in run.stdout.splitlines() if line.startswith(marker)]
        if len(observations) != 1 or set(observations[0]) != {"en", "es-MX"}:
            raise ValueError("missing unique bilingual worker observation")
        snapshot_path = root / "es-MX.json"
        observed = observations[0]["es-MX"]["artifacts"]
        pdf, manifest = verify(json.loads(snapshot_path.read_bytes()), observed)
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    receipt = {
        "schema": "nico.phase9.synthetic-spanish-pdf-proof.v1",
        "checkout_sha": head,
        "workflow_run_id": os.environ["GITHUB_RUN_ID"],
        "workflow_run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "repository": os.environ["GITHUB_REPOSITORY"],
        "worker_probe_sha256": sha256(PROBE.read_bytes()),
        "report_language": "es-MX",
        "report_finality": "automated_draft",
        "client_delivery_allowed": False,
        "synthetic_fixture": True,
        "fixture_report_identity": "owned worker fixture; not the checkout SHA",
        "provider_attestation": "not supplied",
        "deployment_verified": False,
        "pdf_sha256": sha256(pdf),
        "pdf_pages": observed["pages"],
        "pdf_size_bytes": len(pdf),
        "manifest_file_sha256": sha256(manifest_bytes),
        "renderer": {name: version(name) for name in ("pypdf", "Pillow", "reportlab")},
        "python": sys.version.split()[0],
    }
    OUTPUT.mkdir()
    (OUTPUT / "nico-es-MX-synthetic-draft.pdf").write_bytes(pdf)
    (OUTPUT / "artifact-manifest.json").write_bytes(manifest_bytes)
    (OUTPUT / "build-proof.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
