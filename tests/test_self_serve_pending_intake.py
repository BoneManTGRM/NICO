import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, urlsplit

from nico.self_serve_candidate.oauth_callback import begin_authorization, resume_intake
from nico.self_serve_candidate.oauth_state import GithubAppFlow
from nico.self_serve_candidate.oauth_state_store import SQLITE_SCHEMA, SqlOAuthStateStore
from nico.self_serve_candidate.pending_intake import PendingIntake, decode_pending, encode_pending
from nico.self_serve_candidate.provider_download import VerifiedSession


class PendingIntakeRoundTrip(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "pending.db"
        with sqlite3.connect(self.path) as conn:
            conn.execute(SQLITE_SCHEMA)
        self.now = 100
        self.draft = PendingIntake("https://github.com/Example/Project", "María Núñez",
                                   True, "ordinary-v1")
        self.verified = VerifiedSession(42, "synthetic-provider-result")
        self.exchanges = 0

    def store(self):
        return SqlOAuthStateStore(lambda: sqlite3.connect(self.path), dialect="sqlite")

    def flow(self):
        return GithubAppFlow(self.store(), configured_redirect="https://nico.example/callback",
                             clock=lambda: self.now)

    def start(self, *, draft=True):
        begin = begin_authorization(self.flow(), client_id="Example123",
                                    intake=self.draft if draft else None)
        query = parse_qs(urlsplit(begin.location).query)
        self.assertEqual(set(query), {"client_id", "state", "redirect_uri",
                                    "code_challenge", "code_challenge_method"})
        self.assertNotIn("Project", begin.location + begin.cookie)
        self.assertNotIn("ordinary-v1", begin.location + begin.cookie)
        return query["state"][0], begin.cookie.split(";", 1)[0].split("=", 1)[1]

    def exchange(self, code, pending):
        self.exchanges += 1
        self.assertNotIn("María", repr(pending))
        return self.verified

    def finish(self, state, cookie, *, terms="ordinary-v1", exchange=None):
        return resume_intake(self.flow(), codes=["synthetic-code"], states=[state],
                             binding_cookies=[cookie], exchange_verified=exchange or self.exchange,
                             current_terms=terms)

    def test_independent_connection_restores_fields_once_to_bound_browser(self):
        state, cookie = self.start()
        self.assertIsNone(self.finish(state, "Q" * 43))
        self.assertEqual(self.exchanges, 0)
        restored = self.finish(state, cookie)
        self.assertEqual(restored.session, self.verified)
        self.assertEqual(restored.intake, self.draft)
        self.assertNotIn("María", repr(restored))
        self.assertIsNone(self.finish(state, cookie))
        self.assertEqual(self.exchanges, 1)

    def test_changed_terms_keep_form_but_require_fresh_consent(self):
        state, cookie = self.start()
        result = self.finish(state, cookie, terms="ordinary-v2").intake
        self.assertEqual(result.repository, self.draft.repository)
        self.assertEqual(result.full_name, self.draft.full_name)
        self.assertEqual(result.terms_shown, "ordinary-v1")
        self.assertIs(result.permission_attested, False)

    def test_expired_draft_is_not_returned_and_can_be_pruned(self):
        state, cookie = self.start()
        self.now = 400
        self.assertIsNone(self.finish(state, cookie))
        self.assertEqual(self.store().prune_expired(self.now), 1)
        self.assertEqual(self.exchanges, 0)

    def test_missing_or_corrupt_draft_never_resumes(self):
        state, cookie = self.start(draft=False)
        self.assertIsNone(self.finish(state, cookie))
        state, cookie = self.start()
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE nico_self_serve_oauth_pending SET intake_json = ?", ("[0]",))
        self.assertIsNone(self.finish(state, cookie))
        self.assertEqual(self.exchanges, 0)

    def test_failed_provider_exchange_does_not_reopen_attempt(self):
        state, cookie = self.start()
        self.assertIsNone(self.finish(state, cookie, exchange=lambda *_: None))
        self.assertIsNone(self.finish(state, cookie))

    def test_maximum_encoded_fields_round_trip(self):
        draft = PendingIntake("https://github.com/" + "a" * 39 + "/" + "b" * 100,
                              '"' * 200, True, "t" * 64)
        self.assertEqual(decode_pending(encode_pending(draft)), draft)
