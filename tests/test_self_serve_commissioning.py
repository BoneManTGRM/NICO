import unittest

from nico.self_serve_candidate.github_requester_standing import Standing, verify_commissioning_authority


class Commissioning(unittest.TestCase):
    def setUp(self):
        self.inputs = dict(
            authenticated_user={"id": 12, "type": "User", "site_admin": True},
            user_installations=[{"id": 34, "app_id": 56, "suspended_at": None}],
            installation_repositories=[{"id": 78, "permissions": {"pull": True}}],
            expected_actor_id=12, expected_installation_id=34, expected_app_id=56,
            expected_repository_id=78,
        )
        self.repository = {
            "id": 78, "private": False, "owner": {"id": 902, "type": "Organization"},
            "permissions": {"admin": False, "push": True, "pull": True},
        }

    def test_personal_owner(self):
        repo = self.repository | {"owner": {"id": 12, "type": "User"}}
        self.assertEqual(verify_commissioning_authority(repository_details=repo, **self.inputs),
                         Standing(12, 56, 34, 78))

    def test_repository_admin(self):
        repo = self.repository | {"permissions": {"admin": True}}
        self.assertEqual(verify_commissioning_authority(repository_details=repo, **self.inputs),
                         Standing(12, 56, 34, 78))

    def test_read_write_public_site_admin_and_checkbox_are_insufficient(self):
        repo = self.repository | {"attested": True}
        self.assertIsNone(verify_commissioning_authority(repository_details=repo, **self.inputs))

    def test_wrong_repository_does_not_inherit_admin(self):
        repo = self.repository | {"id": 79, "permissions": {"admin": True}}
        self.assertIsNone(verify_commissioning_authority(repository_details=repo, **self.inputs))

    def test_lost_installation_scope_denies_admin(self):
        self.inputs["installation_repositories"] = []
        repo = self.repository | {"permissions": {"admin": True}}
        self.assertIsNone(verify_commissioning_authority(repository_details=repo, **self.inputs))

    def test_organization_id_is_not_a_personal_owner(self):
        repo = self.repository | {"owner": {"id": 12, "type": "Organization"}}
        self.assertIsNone(verify_commissioning_authority(repository_details=repo, **self.inputs))

    def test_malformed_and_unproven_fields_fail_closed(self):
        for patch in ({"owner": {"id": 12, "type": []}}, {"owner": None},
                      {"permissions": {"admin": 1}}, {"permissions": None}):
            with self.subTest(patch=patch):
                self.assertIsNone(verify_commissioning_authority(
                    repository_details=self.repository | patch, **self.inputs))
