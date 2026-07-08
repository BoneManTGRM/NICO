from nico.hosted_dependency_normalization import exact_osv_dependencies, parse_requirements_normalized


def test_parse_requirements_normalizes_extras_for_osv():
    deps = parse_requirements_normalized("PyJWT[crypto]==2.13.0\nuvicorn==0.50.2\nfastapi>=0.139.0\n")

    assert deps[0] == {
        "name": "PyJWT",
        "operator": "==",
        "version": "2.13.0",
        "ecosystem": "PyPI",
        "source": "requirements.txt",
    }
    assert deps[1]["name"] == "uvicorn"
    assert deps[1]["version"] == "0.50.2"
    assert deps[2]["operator"] == ">="


def test_exact_osv_dependencies_excludes_ranges_and_extras_fragments():
    exact = exact_osv_dependencies(
        [
            {"name": "PyJWT", "operator": "==", "version": "2.13.0", "ecosystem": "PyPI"},
            {"name": "Broken", "operator": "", "version": "[crypto]==2.13.0", "ecosystem": "PyPI"},
            {"name": "fastapi", "operator": ">=", "version": "0.139.0", "ecosystem": "PyPI"},
            {"name": "react", "operator": "", "version": "18.3.1", "ecosystem": "npm"},
        ]
    )

    assert exact == [
        {"name": "PyJWT", "version": "2.13.0", "ecosystem": "PyPI"},
        {"name": "react", "version": "18.3.1", "ecosystem": "npm"},
    ]
    assert "[crypto]" not in str(exact)
