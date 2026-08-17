from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_terminal_language_renderer_and_exact_artifact_hashes_share_final_bytes() -> None:
    """Exercise the production wrapper order in an isolated interpreter."""

    repository_root = Path(__file__).resolve().parents[1]
    script = r'''
import base64
import hashlib
from copy import deepcopy

from tests.test_comprehensive_artifact_manifest_approval_v1 import _package
from nico import comprehensive_artifact_manifest_approval_v1 as manifest
from nico import comprehensive_exact_artifact_hash_binding_v1 as binding
from nico.comprehensive_manifest_navigation_v1 import (
    install_comprehensive_manifest_navigation_v1,
)
from nico.comprehensive_spanish_client_surface_localization_v86 import (
    install_comprehensive_spanish_client_surface_localization_v86,
)


install_comprehensive_manifest_navigation_v1()
binding.install_comprehensive_exact_artifact_hash_binding_v1()
localization = install_comprehensive_spanish_client_surface_localization_v86()
assert localization["digest_independent_exact_manifest_guide_preserved"] is True

results = {}
for language in ("en", "es-MX"):
    package = _package()
    package["json"]["identity"]["report_language"] = language
    result = manifest.attach_artifact_manifest(package)
    results[language] = result

    artifact_bytes = {
        "findings_csv": result["findings_csv"].encode("utf-8"),
        "evidence_csv": result["evidence_csv"].encode("utf-8"),
        "candidate_register_json": result["candidate_register_json"].encode("utf-8"),
        "remediation_backlog_json": result["remediation_backlog_json"].encode("utf-8"),
        "markdown_report": result["markdown"].encode("utf-8"),
        "html_report": result["html"].encode("utf-8"),
        "comprehensive_pdf": base64.b64decode(result["pdf_base64"]),
        "canonical_json": result["canonical_json"].encode("utf-8"),
    }
    for item in result["artifact_manifest"]["artifacts"]:
        content = artifact_bytes[item["artifact_type"]]
        assert hashlib.sha256(content).hexdigest() == item["sha256"]
        assert len(content) == item["size_bytes"]

    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False

spanish = results["es-MX"]
assert "## Manifiesto de artefactos del cliente" in spanish["markdown"]
assert "## Registro de revisión humana y aprobación de artefactos exactos" in spanish["markdown"]
assert "## Client Artifact Manifest" not in spanish["markdown"]
assert "## Human Review and Exact-Artifact Approval Record" not in spanish["markdown"]
assert "| Artefacto | Nombre de archivo | SHA-256 |" not in spanish["markdown"]

for field, artifact_type in (("markdown", "markdown_report"), ("html", "html_report")):
    tampered = deepcopy(spanish)
    tampered[field] += "\nmutación posterior al hash\n"
    try:
        binding._validate_exact_artifact_hashes(tampered)
    except ValueError as exc:
        assert str(exc).startswith(f"artifact {artifact_type} SHA-256 mismatch:")
    else:
        raise AssertionError(f"post-hash {field} mutation was not blocked")
'''

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, (
        "isolated terminal artifact-hash proof failed\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
