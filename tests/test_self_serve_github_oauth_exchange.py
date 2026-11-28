import unittest
from urllib.parse import parse_qs

import httpx

from nico.self_serve_candidate.github_oauth_exchange import exchange_github_actor
from nico.self_serve_candidate.oauth_state import Pending


class OAuthExchangeTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.redirect = "https://nico.example/oauth"
        self.token = "ghu_" + "b" * 32
        self.token_response = dict(access_token=self.token, token_type="bearer", scope="",
                                   expires_in=28800, refresh_token="fixture-not-retained")
        self.actor_response = dict(type="User", id=42)
        self.status = 200

    def exchange(self, *, redirect=None):
        def send(req):
            self.calls.append(req)
            if req.method == "POST":
                return httpx.Response(self.status, json=self.token_response,
                                      headers={"Location": "https://other.example/unrelated"})
            return httpx.Response(200, json=self.actor_response)
        with httpx.Client(transport=httpx.MockTransport(send), follow_redirects=True) as client:
            return exchange_github_actor(
                client, client_id="fixture_id", client_secret="syntheticsecret", code="fixture_code",
                pending=Pending(b"0" * 32, self.redirect, 300, "a" * 43),
                configured_redirect=redirect or self.redirect,
            )

    def test_fixed_tls_origins_pkce_and_verified_provider_actor(self):
        session = self.exchange()
        self.assertEqual(session.actor_id, 42)
        self.assertEqual(session.token, self.token)
        self.assertNotIn(self.token, repr(session))
        first, second = self.calls
        self.assertEqual(str(first.url), "https://github.com/login/oauth/access_token")
        self.assertEqual(str(second.url), "https://api.github.com/user")
        self.assertEqual(parse_qs(first.content.decode())["code_verifier"], ["a" * 43])
        self.assertEqual(parse_qs(first.content.decode())["redirect_uri"], [self.redirect])
        self.assertEqual(second.headers["authorization"], "Bearer " + self.token)
        self.assertIsNone(second.headers.get("client_secret"))
        self.assertEqual(first.url.query, b"")

    def test_never_follows_token_service_redirect(self):
        self.status = 302
        self.assertIsNone(self.exchange())
        self.assertEqual(len(self.calls), 1)

    def test_scope_lifetime_and_token_kind_must_match(self):
        for key, bad in (("scope", "repo"), ("expires_in", 0), ("access_token", "ghs_fixture")):
            with self.subTest(key=key):
                value = self.token_response[key]
                self.token_response[key] = bad
                self.calls.clear()
                self.assertIsNone(self.exchange())
                self.assertEqual(len(self.calls), 1)
                self.token_response[key] = value

    def test_bad_actor_or_cross_redirect_denied(self):
        self.assertIsNone(self.exchange(redirect="https://other.example/oauth"))
        self.assertFalse(self.calls)
        self.actor_response = {"type": "Bot", "id": 42}
        self.assertIsNone(self.exchange())
