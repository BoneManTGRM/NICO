"""Synthetic HTTPS cross-site OAuth cookie proof, with every request intercepted."""
from argparse import ArgumentParser
from html import escape
from http.cookies import SimpleCookie
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from playwright.sync_api import sync_playwright

from nico.self_serve_candidate.oauth_callback import (
    begin_authorization, clear_binding_cookie, complete_authorization,
)
from nico.self_serve_candidate.oauth_state import GithubAppFlow
from nico.self_serve_candidate.oauth_state_store import SQLITE_SCHEMA, SqlOAuthStateStore
from nico.self_serve_candidate.provider_download import VerifiedSession

APP = "https://nico.example"
CALLBACK = APP + "/callback"
PROVIDER = "provider.example"


def prove(browser):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "state.db"
        with sqlite3.connect(path) as conn:
            conn.execute(SQLITE_SCHEMA)
        flow = GithubAppFlow(SqlOAuthStateStore(lambda: sqlite3.connect(path), dialect="sqlite"),
                             configured_redirect=CALLBACK, clock=lambda: 100)
        redirects = {}
        fixture_codes = {}
        observations = []
        exchanges = []

        def verified(code, pending):
            assert code in ("fixture-a", "fixture-b") and pending.redirect_uri == CALLBACK
            exchanges.append(code)
            return VerifiedSession(42, "synthetic-token")

        def intercept(route):
            req = route.request
            addr = urlsplit(req.url)
            if req.url in (APP + "/start/a", APP + "/start/b"):
                tab = addr.path[-1]
                start = begin_authorization(flow, client_id="fixture_id")
                authorization = urlsplit(start.location)
                assert (authorization.scheme, authorization.netloc, authorization.path) == (
                    "https", "github.com", "/login/oauth/authorize")
                # Use a reserved hostname: if interception fails no fixture request reaches GitHub.
                redirects[tab] = urlunsplit(authorization._replace(netloc=PROVIDER))
                state = parse_qs(authorization.query)["state"][0]
                fixture_codes[state] = "fixture-" + tab
                # WebKit cannot fulfill a routed redirect. Follow a top-level link instead.
                route.fulfill(status=200, content_type="text/html",
                              headers={"set-cookie": start.cookie},
                              body=f'<a id="strict" href="{APP}/strict/{tab}">Continue</a>')
            elif req.url in (APP + "/strict/a", APP + "/strict/b"):
                url = escape(redirects[addr.path[-1]], quote=True)
                route.fulfill(status=200, content_type="text/html", headers={
                    "set-cookie": "__Host-negative=synthetic; Path=/; Secure; HttpOnly; SameSite=Strict",
                }, body=f'<a id="provider" href="{url}">Continue</a>')
            elif addr.scheme == "https" and addr.netloc == PROVIDER and addr.path == "/login/oauth/authorize":
                state = parse_qs(addr.query)["state"][0]
                url = CALLBACK + "?" + urlencode({"state": state, "code": fixture_codes[state]})
                route.fulfill(status=200, content_type="text/html",
                              body=f'<a id="return" href="{escape(url, quote=True)}">Continue</a>')
            elif addr.scheme == "https" and addr.netloc == "nico.example" and addr.path == "/callback":
                params = parse_qs(addr.query)
                cookies = SimpleCookie(req.all_headers().get("cookie", ""))
                lax = cookies.get("__Host-nico_requester_oauth")
                session = complete_authorization(
                    flow, codes=params.get("code", []), states=params.get("state", []),
                    binding_cookies=[lax.value] if lax else [], exchange_verified=verified)
                observations.append((params["code"][0], lax is not None, "__Host-negative" in cookies,
                                     session is not None))
                # A stale tab must not delete the current tab's binding.
                headers = {"set-cookie": clear_binding_cookie()} if session else {}
                route.fulfill(status=200, content_type="text/plain", headers=headers,
                              body="signed in" if session else "denied")
            else:
                route.abort()

        legitimate = browser.new_context(service_workers="block")
        wrong = browser.new_context(service_workers="block")
        for ctx in legitimate, wrong:
            ctx.route("**/*", intercept)
        tab_a = legitimate.new_page()
        tab_b = legitimate.new_page()
        def depart(page, tab):
            page.goto(APP + "/start/" + tab, timeout=8000)
            page.locator("#strict").click(timeout=8000)
            cookies = {item["name"]: item for item in legitimate.cookies(APP)}
            for name, mode in (("__Host-nico_requester_oauth", "Lax"), ("__Host-negative", "Strict")):
                assert name in cookies, f"fixture cookie was not installed: {name}"
                item = cookies[name]
                assert item["sameSite"] == mode and item["secure"] and item["httpOnly"], name
            binding = cookies["__Host-nico_requester_oauth"]["value"]
            page.locator("#provider").click(timeout=8000)
            return binding

        binding_a = depart(tab_a, "a")
        binding_b = depart(tab_b, "b")
        assert binding_a != binding_b, "second sign-in did not replace the binding"
        stranger = wrong.new_page()
        stranger.goto(redirects["b"], timeout=8000)
        stranger.locator("#return").click(timeout=8000)
        tab_a.locator("#return").click(timeout=8000)
        tab_b.locator("#return").click(timeout=8000)
        tab_b.goto(redirects["b"], timeout=8000)
        tab_b.locator("#return").click(timeout=8000)
        assert observations == [
            ("fixture-b", False, False, False),
            ("fixture-a", True, False, False),
            ("fixture-b", True, False, True),
            ("fixture-b", False, False, False),
        ], observations
        assert exchanges == ["fixture-b"], exchanges
        for ctx in legitimate, wrong:
            ctx.close()


if __name__ == "__main__":
    args = ArgumentParser()
    args.add_argument("--browser", choices=("chromium", "webkit"), default="chromium")
    args.add_argument("--executable")
    options = args.parse_args()
    with sync_playwright() as pw:
        launch = {"headless": True}
        if options.executable:
            launch["executable_path"] = options.executable
        browser = getattr(pw, options.browser).launch(**launch)
        try:
            prove(browser)
        finally:
            browser.close()
    print("Synthetic cross-site return passed: Lax only; wrong browser, stale tab and replay denied.")
