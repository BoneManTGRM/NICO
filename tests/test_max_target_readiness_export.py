from nico.max_target_readiness_export import build_max_target_readiness_export


def test_readiness_export_formats():
    md = build_max_target_readiness_export({}, "markdown")
    js = build_max_target_readiness_export({}, "json")
    bad = build_max_target_readiness_export({}, "txt")

    assert md["status"] == "ok"
    assert js["status"] == "ok"
    assert bad["status"] == "unsupported"
