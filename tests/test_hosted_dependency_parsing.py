from nico.hosted_assessment import parse_requirements


def test_hosted_requirements_do_not_send_extras_as_osv_package_names():
    deps = parse_requirements("PyJWT==2.13.0\ncryptography==46.0.3\n")
    names = {item["name"] for item in deps}
    versions = {item["name"]: item["version"] for item in deps}

    assert "PyJWT" in names
    assert "PyJWT[crypto]" not in names
    assert versions["PyJWT"] == "2.13.0"
    assert versions["cryptography"] == "46.0.3"
