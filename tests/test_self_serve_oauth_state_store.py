from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest

from nico.self_serve_candidate.oauth_state import GithubAppFlow
from nico.self_serve_candidate.oauth_state_store import SQLITE_SCHEMA, SqlOAuthStateStore


class DurableOAuth(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "oauth.db"
        with sqlite3.connect(self.path) as conn:
            conn.execute(SQLITE_SCHEMA)
        self.now = 100
        self.binding = "Z" * 43
        self.redirect = "https://nico.example/callback"

    def flow(self, *, redirect=None):
        store = SqlOAuthStateStore(lambda: sqlite3.connect(self.path), dialect="sqlite")
        return GithubAppFlow(store, configured_redirect=redirect or self.redirect, clock=lambda: self.now)

    def test_single_consume_across_independent_connections(self):
        state = self.flow().begin(trusted_browser_binding=self.binding)["state"]
        barrier = Barrier(2)

        def use(_):
            flow = self.flow()
            barrier.wait(timeout=3)
            return flow.consume(state=state, trusted_browser_binding=self.binding)

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(x is not None for x in pool.map(use, range(2))), 1)
        self.assertIsNone(self.flow().consume(state=state, trusted_browser_binding=self.binding))

    def test_wrong_browser_or_redirect_does_not_burn_state(self):
        state = self.flow().begin(trusted_browser_binding=self.binding)["state"]
        self.assertIsNone(self.flow().consume(state=state, trusted_browser_binding="Y" * 43))
        self.assertIsNone(self.flow(redirect="https://other.example/callback").consume(
            state=state, trusted_browser_binding=self.binding))
        self.assertIsNotNone(self.flow().consume(state=state, trusted_browser_binding=self.binding))

    def test_expired_state_never_consumes(self):
        state = self.flow().begin(trusted_browser_binding=self.binding)["state"]
        self.now = 400
        self.assertIsNone(self.flow().consume(state=state, trusted_browser_binding=self.binding))

    def test_failed_downstream_exchange_does_not_reopen_state(self):
        state = self.flow().begin(trusted_browser_binding=self.binding)["state"]
        self.assertIsNotNone(self.flow().consume(state=state, trusted_browser_binding=self.binding))
        # Simulate the provider failing after consumption. The same callback is unusable.
        self.assertIsNone(self.flow().consume(state=state, trusted_browser_binding=self.binding))
        replacement = self.flow().begin(trusted_browser_binding=self.binding)["state"]
        self.assertNotEqual(replacement, state)
        self.assertIsNotNone(self.flow().consume(state=replacement, trusted_browser_binding=self.binding))
