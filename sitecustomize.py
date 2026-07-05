from __future__ import annotations


def _normalize() -> None:
    try:
        import nico.cli as cli
    except Exception:
        return

    patterns = getattr(cli, "APPSEC_PATTERNS", None)
    if not isinstance(patterns, list):
        return

    out = []
    changed = False
    for item in patterns:
        if isinstance(item, tuple) and len(item) == 6:
            category, severity, title, marker, fix, map_id = item
            biz = "Over-permissioned AI tools can exceed intended access boundaries."
            out.append((category, severity, title, marker, fix, biz, map_id))
            changed = True
        else:
            out.append(item)
    if changed:
        cli.APPSEC_PATTERNS = out


_normalize()
