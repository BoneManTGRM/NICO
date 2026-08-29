from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROOF_SCRIPT = REPOSITORY_ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v3.py"


def test_localized_pdf_transport_source_contract() -> None:
    source = PROOF_SCRIPT.read_text(encoding="utf-8")
    start = source.index("def _fetch_localized_pdf(")
    end = source.index("\ndef _verify_localized_spanish_terminal_artifacts(", start)
    transport_boundary = source[start:end]

    assert "page.request" not in transport_boundary
    assert "httpx.HTTPTransport(verify=True, trust_env=False, retries=0)" in transport_boundary
    assert "follow_redirects=False" in transport_boundary
    assert '"Accept-Encoding": "identity"' in transport_boundary
    assert "response.status_code == 200" in transport_boundary


def test_localized_pdf_transport_behavior_isolated_in_subprocess(tmp_path: Path) -> None:
    scripts = REPOSITORY_ROOT / "scripts"
    program = textwrap.dedent(
        f"""
        from __future__ import annotations

        import hashlib
        import os
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
                raise AssertionError("localized PDF transport proof must not start a browser")

            sync_api_stub.Browser = Browser
            sync_api_stub.Page = Page
            sync_api_stub.sync_playwright = sync_playwright
            playwright_stub.sync_api = sync_api_stub
            sys.modules["playwright"] = playwright_stub
            sys.modules["playwright.sync_api"] = sync_api_stub

        import spanish_comprehensive_live_acceptance_v3 as proof

        expected_text = " ".join(proof._expected_engagement_metadata().values())
        proof.PdfReader = lambda _stream: SimpleNamespace(pages=[object()])
        proof.base._pdf_text = lambda _body: expected_text
        proof.client_evidence_summary_has_five_fields = lambda *_args, **_kwargs: True

        body = b"%PDF-1.7\\nexact localized bytes\\n%%EOF\\n"
        run_id = "comprun_transportproof"

        def response(*, status_code=200, artifact_sha256=None):
            return SimpleNamespace(
                content=body,
                status_code=status_code,
                headers={{
                    "x-nico-run-id": run_id,
                    "x-nico-report-language": "en",
                    "x-nico-assessment-rerun": "false",
                    "x-nico-artifact-sha256": (
                        artifact_sha256 or hashlib.sha256(body).hexdigest()
                    ),
                    "x-nico-canonical-truth-sha256": "a" * 64,
                }},
            )

        observed = {{}}

        def fake_transport(**kwargs):
            observed["transport"] = kwargs
            return object()

        class FakeClient:
            next_response = response()
            calls = []

            def __init__(self, **kwargs):
                observed["client"] = kwargs

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def get(self, url, **kwargs):
                type(self).calls.append((url, kwargs))
                return type(self).next_response

        proof.httpx.HTTPTransport = fake_transport
        proof.httpx.Client = FakeClient

        root = Path.cwd()
        success_dir = root / "success"
        success_dir.mkdir()
        os.chdir(success_dir)
        result = proof._fetch_localized_pdf(
            frontend_origin="https://app.nicoaudit.com",
            run_id=run_id,
            report_language="en",
        )

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
        assert len(FakeClient.calls) == 1
        url, request_options = FakeClient.calls[0]
        assert url == (
            "https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/"
            f"{{run_id}}/localized-report/en/pdf"
        )
        assert request_options == {{
            "headers": {{
                "Accept": "application/pdf",
                "Accept-Encoding": "identity",
                "Cache-Control": "no-store",
            }}
        }}
        assert result["sha256"] == hashlib.sha256(body).hexdigest()
        assert result["size_bytes"] == len(body)
        assert (success_dir / result["artifact_path"]).read_bytes() == body

        for status_code in (206, 302, 503):
            case_dir = root / f"status-{{status_code}}"
            case_dir.mkdir()
            os.chdir(case_dir)
            FakeClient.calls = []
            FakeClient.next_response = response(status_code=status_code)
            try:
                proof._fetch_localized_pdf(
                    frontend_origin="https://app.nicoaudit.com",
                    run_id=run_id,
                    report_language="en",
                )
            except AssertionError as exc:
                assert f"returned HTTP {{status_code}}" in str(exc)
            else:
                raise AssertionError(f"HTTP {{status_code}} was accepted")
            assert len(FakeClient.calls) == 1
            assert not (case_dir / "audit-results").exists()

        mismatch_dir = root / "hash-mismatch"
        mismatch_dir.mkdir()
        os.chdir(mismatch_dir)
        FakeClient.calls = []
        FakeClient.next_response = response(artifact_sha256="b" * 64)
        try:
            proof._fetch_localized_pdf(
                frontend_origin="https://app.nicoaudit.com",
                run_id=run_id,
                report_language="en",
            )
        except AssertionError as exc:
            assert "computed_artifact_sha256" in str(exc)
        else:
            raise AssertionError("localized PDF body/hash mismatch was accepted")
        assert len(FakeClient.calls) == 1
        assert not (mismatch_dir / "audit-results").exists()

        print("isolated localized PDF transport proof passed")
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
    assert "isolated localized PDF transport proof passed" in completed.stdout
