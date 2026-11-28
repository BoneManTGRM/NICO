from dataclasses import replace
import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

from nico.self_serve_candidate.oauth_state import GithubAppFlow
from nico.self_serve_candidate.oauth_state_store import SQLITE_SCHEMA, SqlOAuthStateStore
from nico.self_serve_candidate.prefill_http import PrefillDependencies, requester_prefill_router
from nico.self_serve_candidate.provider_download import VerifiedSession


ORIGIN = "https://app.example"
START = "/requester/self-serve/sign-in"
RETURN = "/requester/self-serve/callback"
FORM = {"repository": "https://github.com/Example/Project", "full_name": "María Núñez",
        "permission_attested": True, "terms_shown": "review-v1"}


class PrefillHTTP(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "pending.db"
        with sqlite3.connect(path) as conn:
            conn.execute(SQLITE_SCHEMA)
        flow = GithubAppFlow(SqlOAuthStateStore(lambda: sqlite3.connect(path), dialect="sqlite"),
                             configured_redirect=ORIGIN + RETURN, clock=lambda: 100)
        self.terms = "review-v1"
        self.handoffs = []
        self.exchanges = 0

        def exchange(code, _pending):
            self.exchanges += 1
            return VerifiedSession(13, "synthetic-session") if code == "fixture" else None

        def handoff(result):
            self.handoffs.append(result)
            return RedirectResponse("/assessment", status_code=303)

        self.app = FastAPI()
        self.client = TestClient(self.app, base_url=ORIGIN, follow_redirects=False)
        self.deps = PrefillDependencies(ORIGIN, "Example123", flow,
                                        lambda: self.terms, exchange, handoff)

    def install(self):
        self.app.include_router(requester_prefill_router(self.deps))

    def start(self):
        r = self.client.post(START, headers={"Origin": ORIGIN}, json=FORM)
        self.assertEqual(r.status_code, 200)
        self.assertIn("no-store", r.headers["cache-control"])
        self.assertIn("HttpOnly", r.headers["set-cookie"])
        self.assertNotIn("María", r.text)
        self.assertNotIn("Project", r.text + r.headers["set-cookie"])
        return parse_qs(urlsplit(r.json()["authorization_url"]).query)["state"][0]

    def test_app_is_unmounted_unless_explicitly_composed(self):
        self.assertEqual(self.client.post(START).status_code, 404)

    def test_private_handoff_fires_once_and_keeps_fields(self):
        self.install()
        state = self.start()
        wrong = TestClient(self.app, base_url=ORIGIN, follow_redirects=False)
        params = {"state": state, "code": "fixture"}
        self.assertEqual(wrong.get(RETURN, params=params).status_code, 403)
        r = self.client.get(RETURN, params=params)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/assessment"))
        self.assertIn("no-store", r.headers["cache-control"])
        self.assertEqual(r.headers["referrer-policy"], "no-referrer")
        self.assertIn("Max-Age=0", r.headers["set-cookie"])
        self.assertNotIn("María", r.text)
        self.assertEqual(self.client.get(RETURN, params=params).status_code, 403)
        self.assertEqual(self.exchanges, 1)
        self.assertEqual(len(self.handoffs), 1)
        restored = self.handoffs[0].intake
        self.assertEqual(restored.full_name, FORM["full_name"])
        self.assertEqual(restored.repository, FORM["repository"])
        self.assertTrue(restored.permission_attested)

    def test_changed_terms_are_not_accepted_by_callback(self):
        self.install()
        state = self.start()
        self.terms = "review-v2"
        r = self.client.get(RETURN, params={"state": state, "code": "fixture"})
        self.assertEqual(r.status_code, 303)
        self.assertEqual(len(self.handoffs), 1)
        self.assertFalse(self.handoffs[0].intake.permission_attested)
        self.assertEqual(self.handoffs[0].intake.full_name, FORM["full_name"])

    def test_post_rejects_cross_origin_stale_terms_and_unchecked_permission(self):
        self.install()
        self.assertEqual(self.client.post(START, headers={"Origin": "https://other.example"},
                                          json=FORM).status_code, 403)
        self.assertEqual(self.client.post(START, headers={"Origin": ORIGIN},
                                          json={**FORM, "terms_shown": "old"}).status_code, 409)
        self.assertEqual(self.client.post(START, headers={"Origin": ORIGIN},
                                          json={**FORM, "permission_attested": False}).status_code, 400)
        self.assertNotIn("María", self.client.post(START, headers={"Origin": ORIGIN},
                         json={**FORM, "permission_attested": "true"}).text)

    def test_mounted_origin_must_match_fixed_callback(self):
        with self.assertRaisesRegex(ValueError, "callback"):
            requester_prefill_router(replace(self.deps, browser_origin="https://other.example"))

    def test_duplicate_binding_cookie_is_rejected_without_consuming_valid_attempt(self):
        self.install()
        state = self.start()
        bound = self.client.cookies.get("__Host-nico_requester_oauth")
        params = {"state": state, "code": "fixture"}
        repeated = "; ".join([f"__Host-nico_requester_oauth={bound}"] * 2)
        denied = self.client.get(RETURN, params=params, headers={"Cookie": repeated})
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn("set-cookie", denied.headers)
        self.assertEqual(self.exchanges, 0)
        self.assertEqual(self.client.get(RETURN, params=params).status_code, 303)
