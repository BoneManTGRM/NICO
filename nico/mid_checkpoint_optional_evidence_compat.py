from typing import Any

_PATCHED = False


def install_mid_checkpoint_optional_evidence_compat() -> dict[str, Any]:
    global _PATCHED
    if _PATCHED:
        return {"installed": True, "idempotent_reuse": True}

    import nico.mid_assessment_api as mid_api

    original = mid_api.mid_assessment_response

    def mid_assessment_response(
        req: mid_api.MidAssessmentRunRequest,
    ) -> dict[str, Any]:
        result = original(req)
        if result.get("optional_evidence_submission"):
            return result
        run_id = str(result.get("run_id") or "")
        if not run_id.startswith("midrun_"):
            return result
        from nico.mid_optional_evidence import issue_mid_evidence_submission_access

        result["optional_evidence_submission"] = issue_mid_evidence_submission_access(
            run_id
        )
        return result

    mid_api.mid_assessment_response = mid_assessment_response
    _PATCHED = True
    return {
        "installed": True,
        "idempotent_reuse": False,
        "checkpoint_preseed_compatible": True,
    }


__all__ = ["install_mid_checkpoint_optional_evidence_compat"]
