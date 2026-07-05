            "github_token_health_details": {
                "token_present": final_result.get("github_token_health", {}).get("token_present"),
                "repo_access": final_result.get("github_token_health", {}).get("repo_access"),
                "contents_access": final_result.get("github_token_health", {}).get("contents_access"),
                "pull_requests_access": final_result.get("github_token_health", {}).get("pull_requests_access"),
                "actions_access": final_result.get("github_token_health", {}).get("actions_access"),
                "rate_limit_remaining": final_result.get("github_token_health", {}).get("rate_limit_remaining"),
            },