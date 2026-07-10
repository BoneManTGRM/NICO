"""Regression guard for API exception-exposure CodeQL cleanup.

PR #213 introduced broad route-level wrapper lambdas. They were well-intended,
but CodeQL expanded them into many duplicate exception-flow alerts. Keep API
exception fixes targeted instead of wrapping every route body.
"""

from pathlib import Path

API_MAIN = Path("nico/api/main.py")


def test_api_does_not_use_broad_route_wrapper_pattern():
    content = API_MAIN.read_text(encoding="utf-8")

    assert "def safe_api_call(" not in content
    assert "def safe_api_await(" not in content
    assert "safe_api_call(lambda" not in content
    assert "return await safe_api_await" not in content


def test_api_keeps_bounded_exception_handler_without_route_wrappers():
    content = API_MAIN.read_text(encoding="utf-8")

    assert "@app.exception_handler(Exception)" in content
    assert "Request failed. Review server logs or diagnostic evidence with authorized access." in content
    assert "def safe_blocked_exception" in content
