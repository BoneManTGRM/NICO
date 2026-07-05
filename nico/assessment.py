    if cicd_audit:
        try:
            cicd_result = cicd_audit(target, github_token_env=github_token_env)
            result["cicd_audit"] = cicd_result
            if cicd_result.get("limitations"):
                result["limitations"].extend(cicd_result["limitations"])
        except Exception as e:
            result["limitations"].append(f"CI/CD audit error: {e}")