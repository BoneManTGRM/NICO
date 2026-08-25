from __future__ import annotations

import base64
import copy
import hashlib
import io

from pypdf import PdfReader

from tests.test_comprehensive_report_package_v2 import _package as rich_package
from tests.test_phase9_comprehensive_report_integration_v1 import _result as phase9_result
from tests.test_v2_premium_report_renderer import _package as small_package
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package
from nico.comprehensive_spanish_client_surface_localization_v86 import (
    install_comprehensive_spanish_client_surface_localization_v86,
)


def _render(package):
    result = rebuild_client_artifacts(copy.deepcopy(package))
    pdf = base64.b64decode(result["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    return result, reader


def _render_phase9(package):
    result = finalize_report_package(copy.deepcopy(package))["report_package"]
    pdf = base64.b64decode(result["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    return result, reader


def _rich_input(language):
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


def _phase9_input(language):
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


def _fingerprint(result, reader):
    output = {}
    for field in ("markdown", "html", "pdf_base64"):
        value = result[field]
        output[field] = (hashlib.sha256(value.encode("utf-8")).hexdigest(), len(value))
    output["pdf_sha256"] = result["pdf_sha256"]
    output["page_count"] = len(reader.pages)
    return output


def test_tmp_print_report_fingerprints_1324() -> None:
    install_comprehensive_spanish_client_surface_localization_v86()
    small_result, small_reader = _render(small_package("en"))
    rich_result, rich_reader = _render(_rich_input("en"))
    phase9_result_value, phase9_reader = _render_phase9(_phase9_input("en"))
    print("NICO1324_SMALL", repr(_fingerprint(small_result, small_reader)), flush=True)
    print("NICO1324_RICH", repr(_fingerprint(rich_result, rich_reader)), flush=True)
    print("NICO1324_PHASE9", repr(_fingerprint(phase9_result_value, phase9_reader)), flush=True)
