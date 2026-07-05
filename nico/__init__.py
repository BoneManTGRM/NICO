__version__ = "0.1.0"


def _repair_appsec_pattern_shapes() -> None:
    """Normalize legacy APPSEC pattern tuples at package import time.

    Some scanner tuples may be missing the business-impact field expected by
    ``nico.cli.scan_text``. This guard keeps the runtime scanner stable until
    the large CLI module is split into smaller scanner modules.
    """
    try:
        from nico import cli as _cli
    except Exception:
        return

    repaired = []
    changed = False
    for pattern in getattr(_cli, "APPSEC_PATTERNS", []):
        if len(pattern) == 6:
            category, severity, title, marker, fix, mapping = pattern
            pattern = (
                category,
                severity,
                title,
                marker,
                fix,
                f"{title} can increase security and operational risk.",
                mapping,
            )
            changed = True
        repaired.append(pattern)

    if changed:
        _cli.APPSEC_PATTERNS[:] = repaired


_repair_appsec_pattern_shapes()
