from base64 import urlsafe_b64encode
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Barrier, Lock
import unittest

from nico.self_serve_candidate.oauth_state import GithubAppFlow


class MemoryTestStore:
    def __init__(self):
        self.rows = {}
        self.lock = Lock()

    def insert_unique(self, key, pending):
        with self.lock:
            if key in self.rows:
                raise ValueError("duplicate")
            self.rows[key] = pending

    def consume_matching(self, key, browser_hash, redirect_uri, now):
        with self.lock:
            result = self.rows.get(key)
            if (result is None or result.browser_hash != browser_hash
                    or result.redirect_uri != redirect_uri or result.expires_at <= now):
                return None
            return self.rows.pop(key)


class OAuth(unittest.TestCase):
    def setUp(self):
        self.now = 100
        self.store = MemoryTestStore()
        self.browser = "b" * 43
        self.redirect = "https://nico.example/oauth/github"
        self.flow = GithubAppFlow(self.store, configured_redirect=self.redirect, clock=lambda: self.now)

    def start(self):
        return self.flow.begin(trusted_browser_binding=self.browser)

    def consume(self, request, browser=None):
        return self.flow.consume(state=request["state"], trusted_browser_binding=browser or self.browser)

    def test_s256_fixed_redirect_verifier_stays_server_side(self):
        r = self.start()
        self.assertEqual(set(r), {"state", "redirect_uri", "code_challenge", "code_challenge_method"})
        self.assertEqual((r["redirect_uri"], r["code_challenge_method"]), (self.redirect, "S256"))
        pending = self.consume(r)
        expected = urlsafe_b64encode(sha256(pending.verifier.encode()).digest()).decode().rstrip("=")
        self.assertEqual(r["code_challenge"], expected)
        self.assertNotIn(pending.verifier, repr(pending))
        self.assertIsNone(self.consume(r))

    def test_wrong_browser_does_not_consume(self):
        r = self.start()
        self.assertIsNone(self.consume(r, "x" * 43))
        self.assertIsNotNone(self.consume(r))

    def test_expiry_at_boundary(self):
        r = self.start()
        self.now = 400
        self.assertIsNone(self.consume(r))

    def test_configured_redirect_cannot_be_changed_in_flight(self):
        r = self.start()
        other = GithubAppFlow(self.store, configured_redirect="https://other.example/oauth/github", clock=lambda: self.now)
        self.assertIsNone(other.consume(state=r["state"], trusted_browser_binding=self.browser))
        self.assertIsNotNone(self.consume(r))

    def test_invalid_redirect_and_state(self):
        for redirect in ("http://nico.example/callback", "https://nico.example/callback?redirect=bad",
                         "https://user@nico.example/callback", "https://nico.example//../callback"):
            with self.subTest(redirect=redirect), self.assertRaises(ValueError):
                GithubAppFlow(self.store, configured_redirect=redirect, clock=lambda: self.now)
        self.assertIsNone(self.consume({"state":"not a state"}))

    def test_only_one_concurrent_consume(self):
        r = self.start()
        barrier = Barrier(2)
        def compete(_):
            barrier.wait(timeout=2)
            return self.consume(r)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(compete, range(2)))
        self.assertEqual(sum(x is not None for x in results), 1)


if __name__ == "__main__":
    unittest.main()
