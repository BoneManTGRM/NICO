from __future__ import annotations

import copy
import hashlib
import json

from tests.test_comprehensive_report_package_v2 import _package as rich_package
from tests.test_phase9_comprehensive_report_integration_v1 import _result as phase9_result
from tests.test_v2_premium_report_renderer import _package as small_package
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package
from nico.comprehensive_spanish_client_surface_localization_v86 import (
    install_comprehensive_spanish_client_surface_localization_v86,
)


def _fingerprint(result: dict) -> dict:
    output: dict[str, object] = {}
    for field in ("markdown", "html", "pdf_base64"):
        value = result[field]
        output[field] = [hashlib.sha256(value.encode("utf-8")).hexdigest(), len(value)]
    output["pdf_sha256"] = result["pdf_sha256"]
    output["page_count"] = result["pdf_page_count"]
    return output


def _rich_input(language: str) -> dict:
    canonical = copy.deepcopy(rich_package()["report_package"]["json"])
    generated_at = "2026-08-04T16:15:00Z"
    canonical.update(
        {
            "report_language": language,
            "locale": language,
            "generated_at": generated_at,
            "generation_timestamp": generated_at,
        }
    )
    canonical["identity"].update(
        {"report_language": language, "generated_at": generated_at}
    )
    canonical["assessment"]["report_language"] = language
    return {"json": canonical}


def _phase9_input(language: str) -> dict:
    package = copy.deepcopy(phase9_result())
    canonical = package["report_package"]["json"]
    canonical.update({"report_language": language, "locale": language})
    canonical["identity"].update(
        {"report_language": language, "locale": language}
    )
    canonical["assessment"].update(
        {"report_language": language, "locale": language}
    )
    return package


def test_report_exact_four_phase_fingerprints_are_recorded() -> None:
    install_comprehensive_spanish_client_surface_localization_v86()
    small_before = rebuild_client_artifacts(copy.deepcopy(small_package("en")))
    rebuild_client_artifacts(copy.deepcopy(small_package("es-MX")))
    small_after = rebuild_client_artifacts(copy.deepcopy(small_package("en")))
    rich = rebuild_client_artifacts(_rich_input("en"))
    phase9 = finalize_report_package(_phase9_input("en"))["report_package"]
    payload = {
        "small_before": _fingerprint(small_before),
        "small_after": _fingerprint(small_after),
        "rich": _fingerprint(rich),
        "phase9": _fingerprint(phase9),
    }
    raise AssertionError("PR1269_FINGERPRINTS=" + json.dumps(payload, sort_keys=True))
