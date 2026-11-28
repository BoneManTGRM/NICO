from dataclasses import replace
import unittest

from nico.self_serve_candidate.download_binding import Principal
from nico.self_serve_candidate.intake_binding import IntakeBinding, bound_retry


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
