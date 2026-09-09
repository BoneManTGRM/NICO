"""Download the existing locale assembler's complete, integrity-bound file family."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from fastapi import Response

from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
from nico.comprehensive_retained_report_export_v1 import retained_report_zip


def localized_evidence_package(status: Mapping[str, Any], language: str) -> Response:
    # The existing projection validates immutable source identity, canonical truth,
    # source artifact integrity and accepted-edition binding before rendering.
    from nico.comprehensive_same_run_locale_report_v1 import build_same_run_locale_report

    projection = build_same_run_locale_report(status, language)
    regenerated = projection["localized_artifact_requires_new_approval"]
    if regenerated:
        family = deepcopy(projection["report"])
        family["json"] = family.get("localized_artifact_json")
        family["canonical_json"] = family.get("localized_artifact_canonical_json")
        family["canonical_json_sha256"] = family.get("localized_artifact_canonical_json_sha256")
    else:
        family = deepcopy(dict(status["reports"]))
    _validate_exact_artifact_hashes(family)
    content = retained_report_zip(family)
    lifecycle = projection["localized_artifact_lifecycle"]
    # Regenerated files retain pending approval even when the source was approved.
    # This read-only download never confers delivery authority.
    headers = {
        "Content-Disposition": f'attachment; filename="nico-{projection["run_id"]}-{projection["report_language"]}-review-files.zip"',
        "Cache-Control": "no-store, private, max-age=0",
        "X-NICO-Run-ID": str(projection["run_id"]),
        "X-NICO-Commit-SHA": str(projection["commit_sha"]),
        "X-NICO-Report-ID": str(projection["source_report_id"]),
        "X-NICO-Report-Language": str(projection["report_language"]),
        "X-NICO-Canonical-Truth-SHA256": str(projection["canonical_truth_sha256"]),
        "X-NICO-Artifact-SHA256": hashlib.sha256(content).hexdigest(),
        "X-NICO-Assessment-Rerun": "false",
        "X-NICO-Approval-Status": str(lifecycle["approval_status"]),
        "X-NICO-Delivery-Status": str(lifecycle["delivery_status"]),
        "X-NICO-Client-Delivery-Allowed": str(lifecycle["client_delivery_allowed"]).lower(),
        "X-NICO-Localized-Artifact-Requires-New-Approval": str(regenerated).lower(),
    }
    return Response(content, media_type="application/zip", headers=headers)
