def approval_requirement_for(category: str, severity: str) -> str:
    if category in {'secret_exposure', 'identity_risk'} or severity in {'critical', 'high'}:
        return 'human_review_required_before_production_change'
    return 'safe_for_local_repair_prompt_generation'
