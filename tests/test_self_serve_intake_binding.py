from dataclasses import replace
import unittest

from nico.self_serve_candidate.download_binding import Principal
from nico.self_serve_candidate.github_requester_standing import Standing
from nico.self_serve_candidate.intake_binding import (
    IntakeBinding, bind_verified_intake, bound_retry,
)


class BindingStore:
    def __init__(self, original):
        self.original = original
        self.reads = 0

    def read_binding(self, run_id):
        self.reads += 1
        return self.original


class IntakeRetry(unittest.TestCase):
    def setUp(self):
        self.binding = IntakeBinding("comprun_" + "a" * 32,
                                     Principal("https://github.com", "12"),
                                     78, "sha256:" + "f" * 64)
        self.store = BindingStore(self.binding)

    def test_same_requester_and_intent_resume_exact_run(self):
        self.assertTrue(bound_retry(replace(self.binding), store=self.store))
        self.assertEqual(self.store.reads, 1)

    def test_other_verified_account_cannot_resume_matching_form(self):
        other = replace(self.binding, requester=Principal("https://github.com","19"))
        self.assertFalse(bound_retry(other, store=self.store))

    def test_new_intent_or_other_repository_never_inherits_reservation(self):
        for change in ({"request_sha256":"sha256:"+"e"*64}, {"repository_id":79},
                       {"run_id":"comprun_"+"b"*32}):
            with self.subTest(change=change):
                self.assertFalse(bound_retry(replace(self.binding, **change), store=self.store))

    def test_malformed_run_is_rejected_without_store_lookup(self):
        for run_id in ("comprun_synthetic", "comprun_"+"A"*32, "comprun_"+"a"*31):
            self.assertFalse(bound_retry(replace(self.binding,run_id=run_id), store=self.store))
        self.assertEqual(self.store.reads, 0)

    def test_missing_active_binding_never_resumes(self):
        self.store.original = None
        self.assertFalse(bound_retry(self.binding, store=self.store))


class VerifiedIntake(unittest.TestCase):
    def setUp(self):
        self.fields = dict(
            authority=Standing(12, 34, 56, 78), source_commit="a" * 40,
            full_name="María de la Cruz", permission_attested=True,
            terms_revision="ordinary-v1",
        )
        self.run = "comprun_" + "a" * 32

    def binding(self, **overrides):
        return bind_verified_intake(self.run, **{**self.fields, **overrides})

    def test_same_normalized_form_and_verified_scope_resume(self):
        earlier = self.binding()
        later = self.binding(full_name="  Mari\u0301a   de la Cruz  ")
        self.assertEqual(earlier.requester, Principal("https://github.com", "12"))
        self.assertTrue(bound_retry(later, store=BindingStore(earlier)))

    def test_a_new_commit_name_terms_or_verified_scope_cannot_resume(self):
        store = BindingStore(self.binding())
        for change in (
            {"source_commit": "b" * 40}, {"full_name": "María de la Rosa"},
            {"terms_revision": "ordinary-v2"}, {"authority": Standing(19, 34, 56, 78)},
            {"authority": Standing(12, 35, 56, 78)}, {"authority": Standing(12, 34, 57, 78)},
            {"authority": Standing(12, 34, 56, 79)},
        ):
            with self.subTest(change=change):
                self.assertFalse(bound_retry(self.binding(**change), store=store))

    def test_no_checkbox_coercion_or_browser_authority(self):
        for change in (
            {"permission_attested": False}, {"permission_attested": 1},
            {"permission_attested": "true"}, {"authority": {"actor_id": 12}},
            {"authority": Standing(True, 34, 56, 78)}, {"source_commit": "main"},
            {"terms_revision": ""}, {"full_name": "   "},
            {"full_name": "Name\nTwo"}, {"full_name": "a" * 201},
        ):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    self.binding(**change)

    def test_invalid_reservation_id_never_binds(self):
        with self.assertRaises(ValueError):
            bind_verified_intake("comprun_synthetic", **self.fields)
