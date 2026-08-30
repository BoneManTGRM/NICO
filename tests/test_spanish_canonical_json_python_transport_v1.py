from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROOF_SCRIPT = REPOSITORY_ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v3.py"


def test_canonical_json_transport_avoids_playwright_socket_idle_timeout() -> None:
    source = PROOF_SCRIPT.read_text(encoding="utf-8")
    helper_start = source.index("def _fetch_canonical_json(")
    helper_end = source.index(
        "\ndef _verify_localized_spanish_terminal_artifacts(", helper_start
    )
    helper = source[helper_start:helper_end]
    verifier_start = helper_end
    verifier_end = source.index("\ndef _commercial_spanish_run_proof(", verifier_start)
    verifier = source[verifier_start:verifier_end]

    assert "page.request" not in helper
    assert "httpx.HTTPTransport(verify=True, trust_env=False, retries=0)" in helper
    assert "CANONICAL_JSON_CONNECT_TIMEOUT_SECONDS = 300.0" in source
    assert "CANONICAL_JSON_READ_TIMEOUT_SECONDS = 300.0" in source
    assert '"Accept-Encoding": "identity"' in helper
    assert '"Cache-Control": "no-store"' in helper
    assert "canonical_bytes = response.content" in helper
    assert "require_canonical_json_digest(" in helper
    assert verifier.count("_fetch_canonical_json(") == 2
    assert "/report/json" not in verifier


def test_canonical_json_transport_behavior_isolated_in_subprocess(tmp_path: Path) -> None:
    scripts = REPOSITORY_ROOT / "scripts"
    program = textwrap.dedent(
        f"""
        from __future__ import annotations

        import json
        import sys
        from pathlib import Path
        from types import ModuleType, SimpleNamespace

        scripts = Path({str(scripts)!r})
        sys.path.insert(0, str(scripts))

        try:
            import playwright.sync_api  # noqa: F401
        except ModuleNotFoundError:
            playwright_stub = ModuleType("playwright")
            sync_api_stub = ModuleType("playwright.sync_api")

            class Browser:
                pass

            class Page:
                pass

            def sync_playwright():
                raise AssertionError("canonical transport proof must not start a browser")

            sync_api_stub.Browser = Browser
            sync_api_stub.Page = Page
            sync_api_stub.sync_playwright = sync_playwright
            playwright_stub.sync_api = sync_api_stub
            sys.modules["playwright"] = playwright_stub
            sys.modules["playwright.sync_api"] = sync_api_stub

        import spanish_comprehensive_live_acceptance_v3 as proof

        run_id = "comprun_canonicaltransport"
        payload = {{"identity": {{"run_id": run_id}}, "large_value": "x" * 1_000_000}}
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        expected_digest = "a" * 64
        observed = {{}}

        def fake_require(value, header):
            assert value == payload
            assert header == expected_digest
            return expected_digest

        proof.require_canonical_json_digest = fake_require

        def fake_transport(**kwargs):
            observed["transport"] = kwargs
            return object()

        class FakeClient:
            status_code = 200
            calls = []

            def __init__(self, **kwargs):
                observed["client"] = kwargs

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def get(self, url, **kwargs):
                type(self).calls.append((url, kwargs))
                return SimpleNamespace(
                    content=body,
                    status_code=type(self).status_code,
                    headers={{"x-nico-canonical-truth-sha256": expected_digest}},
                )

        proof.httpx.HTTPTransport = fake_transport
        proof.httpx.Client = FakeClient

        canonical, header, computed = proof._fetch_canonical_json(
            frontend_origin="https://app.nicoaudit.com",
            run_id=run_id,
        )
        assert canonical == payload
        assert header == expected_digest
        assert computed == expected_digest
        assert observed["transport"] == {{
            "verify": True,
            "trust_env": False,
            "retries": 0,
        }}
        client_options = observed["client"]
        assert client_options["follow_redirects"] is False
        assert client_options["trust_env"] is False
        timeout = client_options["timeout"]
        assert timeout.connect >= 300
        assert timeout.read >= 300
        assert timeout.write == 30
        assert timeout.pool == 30
        assert FakeClient.calls == [(
            "https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/"
            f"{{run_id}}/report/json",
            {{"headers": {{
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Cache-Control": "no-store",
            }}}},
        )]

        for status_code in (206, 302, 503):
            FakeClient.status_code = status_code
            try:
                proof._fetch_canonical_json(
                    frontend_origin="https://app.nicoaudit.com",
                    run_id=run_id,
                )
            except AssertionError as exc:
                assert f"returned HTTP {{status_code}}" in str(exc)
            else:
                raise AssertionError(f"HTTP {{status_code}} was accepted")

        print("isolated canonical JSON transport proof passed")
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", program],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, (
        f"isolated transport proof failed with exit {completed.returncode}\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
    assert "isolated canonical JSON transport proof passed" in completed.stdout
