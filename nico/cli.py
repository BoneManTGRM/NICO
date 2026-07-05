#!/usr/bin/env python3
"""
NICO CLI - APPSEC pattern definitions (source-clean state).

All tuples are now consistently 7 values: (id, severity, title, marker, fix, business_impact, mapping).
No runtime normalization required.
"""

APPSEC_PATTERNS = [
    (
        "unsafe_eval",
        "critical",
        "Unsafe eval usage",
        "eval(",
        "Replace eval with a safe parser or allowlist.",
        "User-controlled eval can lead to code execution.",
        "CWE-95",
    ),
    (
        "debug_mode",
        "high",
        "Debug mode enabled",
        "debug=True",
        "Disable debug mode outside local fixtures.",
        "Debug mode can expose internals.",
        "CWE-489",
    ),
    (
        "missing_rate_limit",
        "medium",
        "Rate limiting TODO",
        "TODO: add rate limiting",
        "Add rate limiting and abuse detection.",
        "Missing throttling increases abuse risk.",
        "CWE-307",
    ),
    (
        "insecure_webhook",
        "high",
        "Webhook signature missing",
        "TODO: verify signature",
        "Verify webhook signatures and add replay protection.",
        "Unsigned webhooks can allow forged events.",
        "CWE-345",
    ),
    (
        "unsafe_file_upload",
        "high",
        "Unsafe upload fixture",
        "TODO: validate upload",
        "Validate file type, size, name, and storage path.",
        "Unsafe upload handling can expose data or execution paths.",
        "CWE-434",
    ),
    (
        "ai_agent_permission_drift",
        "high",
        "AI over-permission fixture",
        "over_permissive_tools = True",
        "Restrict AI-agent tools to least privilege.",
        "Over-permissioned AI tools can exceed intended access boundaries, enabling unauthorized actions or data exposure.",
        "OWASP-LLM-A06",
    ),
]

def main() -> None:
    print("NICO CLI - source-clean APPSEC patterns loaded.")

if __name__ == "__main__":
    main()
