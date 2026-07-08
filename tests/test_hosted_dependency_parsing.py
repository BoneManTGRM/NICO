from nico.hosted_assessment import parse_requirements


def test_hosted_requirements_normalize_extras_before_osv_package_lookup():
    deps = parse_requirements("PyJWT[crypto]==2.13.0\n")
    names = {item["name"] for item in deps}
    versions = {item["name"]: item["version"] for item in deps}

    assert "PyJWT" in names
    assert "PyJWT[crypto]" not in names
    assert versions["PyJWT"] == "2.13.0"
