import unittest
from nico.self_serve_candidate.github_requester_standing import Standing, verify_standing


class Admission(unittest.TestCase):
    def setUp(self):
        self.args = dict(
            authenticated_user={"id": 12, "type": "User", "login": "old"},
            user_installations=[{"id": 34, "app_id": 56, "suspended_at": None}],
            installation_repositories=[{"id": 78, "permissions": {"pull": True}, "private": False}],
            expected_actor_id=12, expected_installation_id=34, expected_app_id=56,
            expected_repository_id=78,
        )

    def test_exact_explicit_standing(self):
        self.assertEqual(verify_standing(**self.args), Standing(12, 56, 34, 78))
        self.args["authenticated_user"]["login"] = "new"
        self.assertEqual(verify_standing(**self.args), Standing(12, 56, 34, 78))

    def test_public_visibility_and_attestation_are_not_permission(self):
        self.args["installation_repositories"] = [{"id": 78, "private": False, "authorized": True}]
        self.assertIsNone(verify_standing(**self.args))

    def test_wrong_actor_app_installation_and_repo(self):
        for key in ["expected_actor_id", "expected_app_id", "expected_installation_id", "expected_repository_id"]:
            with self.subTest(key=key):
                self.assertIsNone(verify_standing(**(self.args | {key: 99})))

    def test_no_installation_overlap(self):
        self.assertIsNone(verify_standing(**(self.args | {"user_installations": []})))

    def test_suspended_or_ambiguous_installation(self):
        installation = self.args["user_installations"][0]
        for rows in ([installation | {"suspended_at": "now"}], [installation, installation]):
            self.assertIsNone(verify_standing(**(self.args | {"user_installations": rows})))

    def test_bool_and_non_boolean_pull_never_coerce(self):
        self.assertIsNone(verify_standing(**(self.args | {"expected_actor_id": True})))
        self.args["installation_repositories"][0]["permissions"]["pull"] = 1
        self.assertIsNone(verify_standing(**self.args))

    def test_conflicting_duplicate_repository(self):
        r = self.args["installation_repositories"][0]
        self.assertIsNone(verify_standing(**(self.args | {"installation_repositories": [r, r | {"permissions": {"pull": False}}]})))


if __name__ == "__main__":
    unittest.main()
