from __future__ import annotations

from nico.full_assessment_orchestrator import FULL_ASSESSMENT_STEPS, normalize_repository_target, run_full_assessment_orchestration


def test_normalize_repository_target_accepts_owner_repo_and_github_url() -> None:
    assert normalize_repository_target({"repository": "BoneManTGRM/NICO"}) == "BoneManTGRM/NICO"
    assert normalize_repository_target({"target": "https://github.com/BoneManTGRM/NICO"}) == "BoneManTGRM/NICO"
    assert normalize_repository_target({"target": "https://example.com/BoneManTGRM/NICO"}) == ""


def test_full_assessment_blocks_without_authorization() -> None:
    called: list[str] = []

    result = run_full_assessment_orchestration(
        {"repository": "BoneManTGRM/NICO", "authorization_confirmed": False},
        handlers={"repo_evidence": lambda _context, _outputs: called.append("repo_evidence") or {"status": "complete"}},
    )

    assert result["status"] == "blocked"
    assert result["human_review_required"] is True
    assert result["client_ready"] is False
    assert result["progress"] == [
        {"step": "authorization", "status": "blocked", "message": "Authorization confirmation is required before assessment."}
    ]
    assert called == []


def test_full_assessment_blocks_invalid_repository_target() -> None:
    result = run_full_assessment_orchestration({"repository": "https://example.com/nope", "authorization_confirmed": True})

    assert result["status"] == "blocked"
    assert result["repository"] == ""
    assert result["progress"][0]["step"] == "authorization"
    assert result["progress"][0]["status"] == "blocked"


def test_full_assessment_skeleton_preserves_step_order_and_response_shape() -> None:
    called: list[str] = []

    def handler(step: str):
        def _run(_context: dict, _outputs: dict) -> dict:
            called.append(step)
            if step == "scoring":
                return {"status": "complete", "assessment": {"maturity_signal": {"level": "Senior", "score": 91}}}
            if step == "reports":
                return {"status": "complete", "reports": {"markdown": "# NICO", "html": "<h1>NICO</h1>", "pdf_base64": "abc"}}
            if step == "approval_request":
                return {"status": "complete", "approval": {"approval_id": "approval_123", "status": "pending"}}
            return {"status": "complete"}

        return _run

    handlers = {step: handler(step) for step in FULL_ASSESSMENT_STEPS if step != "authorization"}
    result = run_full_assessment_orchestration(
        {
            "repository": "https://github.com/BoneManTGRM/NICO",
            "authorization_confirmed": True,
            "authorized_by": "frontend_reviewer",
            "customer_id": "cust-a",
            "project_id": "proj-a",
        },
        handlers=handlers,
    )

    assert result["status"] == "complete"
    assert result["repository"] == "BoneManTGRM/NICO"
    assert result["customer_id"] == "cust-a"
    assert result["project_id"] == "proj-a"
    assert result["human_review_required"] is True
    assert result["client_ready"] is False
    assert [item["step"] for item in result["progress"]] == FULL_ASSESSMENT_STEPS
    assert [item["status"] for item in result["progress"]] == ["complete"] * len(FULL_ASSESSMENT_STEPS)
    assert called == FULL_ASSESSMENT_STEPS[1:]
    assert result["assessment"]["maturity_signal"]["score"] == 91
    assert result["reports"]["pdf_base64"] == "abc"
    assert result["approval"]["approval_id"] == "approval_123"


def test_missing_handlers_are_planned_not_faked_complete() -> None:
    result = run_full_assessment_orchestration({"repository": "BoneManTGRM/NICO", "authorization_confirmed": True})

    assert result["status"] == "planned"
    assert result["progress"][0]["status"] == "complete"
    assert all(item["status"] == "planned" for item in result["progress"][1:])
    assert result["assessment"] == {}
    assert result["reports"]["pdf_base64"] == ""
    assert result["approval"]["status"] == "not_requested"
