__version__ = "0.1.0"


def _normalize_appsec_patterns() -> None:
    try:
        from . import cli as _cli
    except Exception:
        return

    patterns = getattr(_cli, "APPSEC_PATTERNS", None)
    if not isinstance(patterns, list):
        return

    normalized = []
    changed = False

    for item in patterns:
        if isinstance(item, tuple) and len(item) == 6:
            category, severity, title, marker, fix, map_id = item
            if category == "ai_agent_permission_drift":
                business_impact = "Over-permissioned AI tools can exceed intended access boundaries."
            else:
                business_impact = f"{title} can increase application security risk."
            normalized.append((category, severity, title, marker, fix, business_impact, map_id))
            changed = True
        else:
            normalized.append(item)

    if changed:
        _cli.APPSEC_PATTERNS = normalized


_normalize_appsec_patterns()
