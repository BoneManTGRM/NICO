from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_emit_isolated_post_fix_english_golden_fingerprints() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    script = r'''
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


def fingerprint(result):
    output = {}
    for field in ("markdown", "html", "pdf_base64"):
        value = result[field]
        output[field] = (hashlib.sha256(value.encode("utf-8")).hexdigest(), len(value))
    output["pdf_sha256"] = result["pdf_sha256"]
    output["page_count"] = result["pdf_page_count"]
    return output


def render(package):
    return rebuild_client_artifacts(copy.deepcopy(package))


def rich_input(language):
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


def phase9_input(language):
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


install_comprehensive_spanish_client_surface_localization_v86()
fingerprints = {
    "SMALL_ENGLISH_GOLDEN": fingerprint(render(small_package("en"))),
    "RICH_ENGLISH_GOLDEN": fingerprint(render(rich_input("en"))),
    "PHASE9_ENGLISH_GOLDEN": fingerprint(
        finalize_report_package(phase9_input("en"))["report_package"]
    ),
}
print("ISOLATED_POST_FIX_GOLDENS=" + json.dumps(fingerprints, sort_keys=True))
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    raise AssertionError(completed.stdout.strip())
