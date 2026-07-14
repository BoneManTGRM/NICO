from nico.assessment_block_messages import assessment_block_detail


def test_generic_workflow_authorization_block_keeps_existing_policy_message() -> None:
    detail = assessment_block_detail(
        {
            "status": "blocked",
            "repository": "BoneManTGRM/NICO",
            "error": "Explicit authorization is required before NICO runs this workflow.",
        }
    )

    assert detail == {
        "status": "blocked",
        "code": "blocked",
        "message": "Request blocked by NICO safety, authorization, or review policy.",
    }


def test_explicit_generic_authorization_code_does_not_expand_shared_route_scope() -> None:
    detail = assessment_block_detail(
        {
            "status": "blocked",
            "code": "authorization_required",
            "error": "Authorization is required for a non-assessment workflow.",
        }
    )

    assert detail["code"] == "blocked"
    assert detail["message"] == "Request blocked by NICO safety, authorization, or review policy."
