from nico.hosted_assessment import parse_requirements, query_osv


class _Response:
    status_code = 200

    def json(self):
        return {"results": [{"vulns": []}, {"vulns": []}]}


def test_parse_requirements_strips_extras_before_osv_queries():
    deps = parse_requirements("PyJWT[crypto]==2.13.0\nuvicorn==0.50.2\n")
    assert deps[0] == {
        "name": "PyJWT",
        "operator": "==",
        "version": "2.13.0",
        "ecosystem": "PyPI",
        "source": "requirements.txt",
    }
    assert deps[1]["name"] == "uvicorn"
    assert deps[1]["version"] == "0.50.2"


def test_query_osv_only_uses_exact_normalized_versions(monkeypatch):
    seen = {}

    def fake_post(url, json, timeout):
        seen["json"] = json
        return _Response()

    monkeypatch.setattr("nico.hosted_assessment.requests.post", fake_post)
    evidence, unavailable = query_osv(
        [
            {"name": "PyJWT", "operator": "==", "version": "2.13.0", "ecosystem": "PyPI"},
            {"name": "fastapi", "operator": ">=", "version": "0.139.0", "ecosystem": "PyPI"},
        ]
    )

    assert unavailable == []
    assert "no vulnerability records" in evidence[0]
    assert seen["json"]["queries"] == [
        {"package": {"name": "PyJWT", "ecosystem": "PyPI"}, "version": "2.13.0"}
    ]
    assert "[crypto]" not in str(seen["json"])
