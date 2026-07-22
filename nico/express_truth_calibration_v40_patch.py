from __future__ import annotations

import re
from typing import Any

VERSION = "nico.express_truth_calibration.v40.patch"


def install_express_truth_calibration_v40_patch() -> dict[str, Any]:
    from nico import express_pdf_score_assurance_v1 as pdf_score
    from nico import express_truth_calibration_v38_compat as compat

    original = getattr(compat._prepare_eslint_truth, "_nico_original", compat._prepare_eslint_truth)

    def prepare(result: dict[str, Any]) -> None:
        section = compat._static_section(result)
        if section:
            cleaned = []
            for raw in section.get("unavailable") or []:
                value = str(raw or "")
                # The v36 parser splits aggregate analyzer names on commas and
                # slashes. Remove punctuation attached to the final analyzer token
                # so `eslint.` is correctly recognized as `eslint` and can be
                # excluded when the repository has no ESLint configuration.
                if "accepted clean execution evidence unavailable for:" in value.casefold():
                    prefix, names = value.split(":", 1)
                    names = ", ".join(
                        re.sub(r"[^a-z0-9_-]+$", "", item.strip(), flags=re.I)
                        for item in re.split(r"[,/]", names)
                        if item.strip()
                    )
                    value = f"{prefix}: {names}"
                cleaned.append(value)
            section["unavailable"] = cleaned
        original(result)

    setattr(prepare, "_nico_original", original)
    compat._prepare_eslint_truth = prepare

    # v38 intentionally reuses one in-place replacement helper for both the
    # renderer and record projection. Expose it on the score-assurance module for
    # the compatibility branch, matching the module contract expected by the
    # bound record function.
    pdf_score._apply_in_place = compat._apply_in_place

    return {
        "status": "installed",
        "version": VERSION,
        "pdf_record_projection_binding_repaired": True,
        "aggregate_analyzer_token_punctuation_normalized": True,
        "eslint_inapplicability_is_order_and_punctuation_independent": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_express_truth_calibration_v40_patch"]
