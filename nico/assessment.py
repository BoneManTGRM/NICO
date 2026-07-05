    # GitHub Token Health (run early, before Activity and CI)
    if github_token_health:
        try:
            token_health = github_token_health(target, github_token_env=github_token_env)
            result["github_token_health"] = token_health
            if token_health.get("limitations"):
                result["limitations"].extend(token_health["limitations"])
            if token_health.get("status") in ("completed", "limited"):
                result["evidence_sources"].append("github_token_health")
        except Exception as e:
            result["limitations"].append(f"GitHub token health error: {e}")