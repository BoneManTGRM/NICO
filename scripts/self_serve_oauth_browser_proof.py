"""Synthetic OAuth proof using two real, loopback-only HTTPS sites."""
from argparse import ArgumentParser
from contextlib import ExitStack, contextmanager
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sqlite3
import ssl
import subprocess
import tempfile
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from playwright.sync_api import sync_playwright

from nico.self_serve_candidate.oauth_callback import (
    begin_authorization, clear_binding_cookie, resume_intake,
)
from nico.self_serve_candidate.oauth_state import GithubAppFlow
from nico.self_serve_candidate.oauth_state_store import SQLITE_SCHEMA, SqlOAuthStateStore
from nico.self_serve_candidate.pending_intake import PendingIntake
from nico.self_serve_candidate.provider_download import VerifiedSession

BINDING = "__Host-nico_requester_oauth"
CONTROL = "__Host-negative"
REGISTERED_CALLBACK = "https://nico.example/callback"


@contextmanager
def https_site(host, tls, respond):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log OAuth query strings or cookies.

        def do_GET(self):
            status, headers, body = respond(urlsplit(self.path), self.headers)
            raw = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

    with ThreadingHTTPServer((host, 0), Handler) as server:
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"https://{host}:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=3)


def fixture_tls(directory):
    key, certificate = directory / "key", directory / "cert"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-subj", "/CN=NICO loopback fixture",
         "-addext", "subjectAltName=IP:127.0.0.1,IP:127.0.0.2",
         "-keyout", str(key), "-out", str(certificate)],
        check=True, timeout=15, capture_output=True,
    )
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, key)
    return tls


def link(identifier, url):
    return f'<a id="{identifier}" href="{escape(url, quote=True)}">Continue</a>'


def prove(browser):
    with ExitStack() as stack:
        directory = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        path = directory / "state.db"
        with sqlite3.connect(path) as conn:
            conn.execute(SQLITE_SCHEMA)
        tls = fixture_tls(directory)
        redirects, fixture_codes = {}, {}
        observations, exchanges, restored = [], [], []
        drafts = {
            "a": PendingIntake("Example/First", "María Núñez", True, "ordinary-v1"),
            "b": PendingIntake("Example/Second", "José Pérez", True, "ordinary-v1"),
        }

        def verified(code, pending):
            assert code in ("fixture-a", "fixture-b") and pending.redirect_uri == REGISTERED_CALLBACK
            exchanges.append(code)
            return VerifiedSession(42, "synthetic-token")

        def app_response(addr, headers):
            request_cookies = SimpleCookie(headers.get("Cookie", ""))
            if addr.path in ("/start/a", "/start/b"):
                tab = addr.path[-1]
                start = begin_authorization(flow, client_id="fixture_id", intake=drafts[tab])
                assert drafts[tab].full_name not in start.location + start.cookie
                assert drafts[tab].repository not in start.location + start.cookie
                authorization = urlsplit(start.location)
                assert (authorization.scheme, authorization.netloc, authorization.path) == (
                    "https", "github.com", "/login/oauth/authorize")
                assert parse_qs(authorization.query)["redirect_uri"] == [REGISTERED_CALLBACK]
                redirects[tab] = urlunsplit(authorization._replace(netloc=urlsplit(provider).netloc))
                fixture_codes[parse_qs(authorization.query)["state"][0]] = "fixture-" + tab
                return 302, {"Location": f"{app}/strict/{tab}", "Set-Cookie": start.cookie}, ""
            if addr.path in ("/strict/a", "/strict/b"):
                return 200, {"Set-Cookie": f"{CONTROL}=synthetic; Path=/; Secure; HttpOnly; SameSite=Strict"}, link(
                    "control", f"{app}/control/{addr.path[-1]}")
            if addr.path in ("/control/a", "/control/b"):
                if BINDING not in request_cookies or CONTROL not in request_cookies:
                    return 400, {}, "Same-site cookie control failed"
                return 200, {}, link("provider", redirects[addr.path[-1]])
            if addr.path == "/callback":
                params = parse_qs(addr.query)
                binding = request_cookies.get(BINDING)
                result = resume_intake(
                    flow, codes=params.get("code", []), states=params.get("state", []),
                    binding_cookies=[binding.value] if binding else [], exchange_verified=verified,
                    current_terms="ordinary-v2")
                if result:
                    restored.append(result.intake)
                observations.append((params["code"][0], binding is not None,
                                     CONTROL in request_cookies, result is not None))
                return (200, {"Set-Cookie": clear_binding_cookie()}, "signed in") if result else (200, {}, "denied")
            return 404, {}, "Not found"

        def provider_response(addr, _headers):
            state = parse_qs(addr.query).get("state", [""])[0]
            if addr.path != "/login/oauth/authorize" or state not in fixture_codes:
                return 404, {}, "Not found"
            url = callback + "?" + urlencode({"state": state, "code": fixture_codes[state]})
            return 200, {}, link("return", url)

        app = stack.enter_context(https_site("127.0.0.1", tls, app_response))
        provider = stack.enter_context(https_site("127.0.0.2", tls, provider_response))
        # The mock provider maps the canonical registered URI to the
        # actual test listener. Production rejects arbitrary callback ports.
        callback = app + "/callback"
        flow = GithubAppFlow(SqlOAuthStateStore(lambda: sqlite3.connect(path), dialect="sqlite"),
                             configured_redirect=REGISTERED_CALLBACK, clock=lambda: 100)
        # Trust only the temporary fixture within these fresh browser contexts.
        legitimate = browser.new_context(ignore_https_errors=True, service_workers="block")
        stack.callback(legitimate.close)
        wrong = browser.new_context(ignore_https_errors=True, service_workers="block")
        stack.callback(wrong.close)

        def depart(page, tab):
            page.goto(app + "/start/" + tab, timeout=8000)
            page.locator("#control").click(timeout=8000)
            cookies = {item["name"]: item for item in legitimate.cookies(app)}
            for name, mode in ((BINDING, "Lax"), (CONTROL, "Strict")):
                assert name in cookies, f"fixture cookie was not installed: {name}"
                item = cookies[name]
                assert item["sameSite"] == mode and item["secure"] and item["httpOnly"], name
            page.locator("#provider").click(timeout=8000)
            return cookies[BINDING]["value"]

        tab_a, tab_b = legitimate.new_page(), legitimate.new_page()
        assert depart(tab_a, "a") != depart(tab_b, "b"), "second sign-in did not rotate the binding"
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
        assert restored == [PendingIntake("Example/Second", "José Pérez", False, "ordinary-v1")]


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
    print("Synthetic HTTPS cross-site return passed: Lax only; wrong browser, stale tab and replay denied.")
