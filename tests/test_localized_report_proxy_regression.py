from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROXY_ROUTE = ROOT / "apps" / "web" / "app" / "api" / "nico" / "[...path]" / "route.ts"
LOCALIZED_REPORT = ROOT / "nico" / "comprehensive_same_run_locale_report_v1.py"


def test_same_run_localized_report_routes_are_reachable_through_same_origin_proxy() -> None:
    proxy = PROXY_ROUTE.read_text(encoding="utf-8")
    backend = LOCALIZED_REPORT.read_text(encoding="utf-8")

    assert 'ROUTE = "/assessment/comprehensive-run/{run_id}/localized-report/{report_language}"' in backend
    assert 'PDF_ROUTE = f"{ROUTE}/pdf"' in backend
    assert 'SUPPORTED_REPORT_LANGUAGES = ("en", "es-MX")' in backend

    assert 'const COMPREHENSIVE_LOCALIZED_REPORT' in proxy
    assert 'localized-report\\/(?:en|es-MX)(?:\\/pdf)?$/' in proxy
    assert 'if (method === "GET" && COMPREHENSIVE_LOCALIZED_REPORT.test(path)) return true;' in proxy
    assert 'method === "POST" && COMPREHENSIVE_LOCALIZED_REPORT.test(path)' not in proxy


def test_localized_reports_keep_exact_run_artifact_transport_policy_and_metadata() -> None:
    proxy = PROXY_ROUTE.read_text(encoding="utf-8")

    assert 'COMPREHENSIVE_REPORT_ARTIFACT.test(path) || COMPREHENSIVE_LOCALIZED_REPORT.test(path)' in proxy
    assert 'retryDelaysMs: ARTIFACT_RETRY_DELAYS_MS' in proxy
    assert 'readClass: "exact-run-artifact"' in proxy
    assert '"content-disposition"' in proxy
    assert '"x-nico-run-id"' in proxy
    assert '"x-nico-report-language"' in proxy
    assert '"x-nico-assessment-rerun"' in proxy
    assert '"x-nico-canonical-truth-sha256"' in proxy
    assert 'request.headers.get("authorization")' not in proxy
    assert 'request.headers.get("cookie")' not in proxy
