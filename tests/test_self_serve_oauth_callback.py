from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import parse_qs, urlsplit
import unittest
from unittest.mock import Mock

from nico.self_serve_candidate.oauth_callback import begin_authorization, complete_authorization, clear_binding_cookie
from nico.self_serve_candidate.oauth_state import GithubAppFlow
from nico.self_serve_candidate.oauth_state_store import SQLITE_SCHEMA, SqlOAuthStateStore
from nico.self_serve_candidate.provider_download import VerifiedSession


class CallbackTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "state"
        with sqlite3.connect(path) as conn:
            conn.execute(SQLITE_SCHEMA)
        self.flow = GithubAppFlow(SqlOAuthStateStore(lambda: sqlite3.connect(path), dialect="sqlite"),
                                  configured_redirect="https://nico.example/callback", clock=lambda: 100)
        self.start = begin_authorization(self.flow, client_id="fixture_id")
        self.url = urlsplit(self.start.location)
        self.state = parse_qs(self.url.query)["state"][0]
        self.binding = self.start.cookie.split(";", 1)[0].split("=", 1)[1]
        self.exchange = Mock(return_value=VerifiedSession(42, "fixture"))

    def finish(self, *, codes=None, states=None, cookies=None):
        return complete_authorization(
            self.flow, codes=["synthetic"] if codes is None else codes,
            states=[self.state] if states is None else states,
            binding_cookies=[self.binding] if cookies is None else cookies,
            exchange_verified=self.exchange)

    def test_provider_redirect_and_temporary_cookie(self):
        self.assertEqual((self.url.scheme, self.url.netloc, self.url.path),
                         ("https", "github.com", "/login/oauth/authorize"))
        self.assertNotIn(self.binding, self.url.query)
        self.assertIn("Secure; HttpOnly; SameSite=Lax", self.start.cookie)
        self.assertTrue(self.start.cookie.startswith("__Host-"))
        self.assertNotIn("Domain=", self.start.cookie)
        self.assertIn("Max-Age=0", clear_binding_cookie())

    def test_wrong_browser_and_duplicate_inputs_never_call_provider(self):
        for inputs in (dict(cookies=["Z" * 43]), dict(cookies=[]),
                       dict(codes=["a", "b"]), dict(states=[self.state, self.state])):
            self.assertIsNone(self.finish(**inputs))
        self.exchange.assert_not_called()
        self.assertEqual(self.finish().actor_id, 42)

    def test_success_can_only_establish_one_session(self):
        self.assertEqual(self.finish().actor_id, 42)
        self.assertIsNone(self.finish())
        self.exchange.assert_called_once()

    def test_provider_failure_never_reopens_attempt(self):
        self.exchange.return_value = None
        self.assertIsNone(self.finish())
        self.assertIsNone(self.finish())
        self.exchange.assert_called_once()
