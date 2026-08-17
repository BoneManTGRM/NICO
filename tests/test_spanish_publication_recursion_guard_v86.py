from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_terminal_spanish_localization_does_not_close_provider_wrapper_cycle() -> None:
    """Reproduce the production wrapper topology in an isolated interpreter.

    A pre-existing completion wrapper delegates dynamically to the provider alias.
    v85 used to replace that provider alias with its new terminal wrapper, closing a
    recursive loop. v86 must leave the provider alias owned by the previous layer.
    """

    repository_root = Path(__file__).resolve().parents[1]
    script = r'''
from nico import client_pdf_status_sanitizer_v1 as sanitizer
from nico import client_report_completion_v2 as completion
from nico import comprehensive_client_ready_projection_v1 as projection
from nico import comprehensive_client_review_companion_v5 as review_v5
from nico import comprehensive_client_review_companion_v7 as review_v7


def provider_compact_client_markdown(canonical, *args, **kwargs):
    return "# Executive Summary\n\nDRAFT · HUMAN REVIEW REQUIRED\n"


def prior_completion_wrapper(canonical, *args, **kwargs):
    # This models the stacked compatibility wrappers in production: the older
    # completion layer dynamically delegates to the provider module at call time.
    return projection.compact_client_markdown(canonical, *args, **kwargs)


projection.compact_client_markdown = provider_compact_client_markdown
completion.compact_client_markdown = prior_completion_wrapper

from nico.comprehensive_spanish_client_surface_localization_v86 import (
    install_comprehensive_spanish_client_surface_localization_v86,
)

provider_bindings = {
    "review_merge": review_v5.merge_substantive_review_markdown,
    "compact_markdown": projection.compact_client_markdown,
    "register_pdf": projection.render_compact_finding_register_pdf,
    "gate_pdf": projection.render_evidence_review_gate_pdf,
    "review_pdf": review_v7.render_paired_substantive_review_pdf,
    "status_sanitizer": sanitizer.sanitize_client_pdf_status,
}

state = install_comprehensive_spanish_client_surface_localization_v86()
assert state["provider_alias_cycle_prevention"] is True
assert state["terminal_consumer_aliases_only"] is True
assert review_v5.merge_substantive_review_markdown is provider_bindings["review_merge"]
assert projection.compact_client_markdown is provider_bindings["compact_markdown"]
assert projection.render_compact_finding_register_pdf is provider_bindings["register_pdf"]
assert projection.render_evidence_review_gate_pdf is provider_bindings["gate_pdf"]
assert review_v7.render_paired_substantive_review_pdf is provider_bindings["review_pdf"]
assert sanitizer.sanitize_client_pdf_status is provider_bindings["status_sanitizer"]

localized = completion.compact_client_markdown({"report_language": "es-MX"})
assert "BORRADOR AUTOMATIZADO" in localized
assert "HUMAN REVIEW REQUIRED" not in localized
'''

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, (
        "isolated Spanish publication recursion proof failed\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
