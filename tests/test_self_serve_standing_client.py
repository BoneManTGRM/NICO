import unittest

import httpx

from nico.self_serve_candidate.github_requester_standing import Standing
from nico.self_serve_candidate.github_standing_client import check_requester


class ProviderContract(unittest.TestCase):
    def setUp(self):
        self.repo = {"id": 78, "owner": {"id": 90, "type": "Organization"},
                     "permissions": {"pull": True, "admin": True}}
        self.responses = {
            "/user": {"id": 12, "type": "User"},
            "/user/installations": {"total_count": 1, "installations":
                                     [{"id": 34, "app_id": 56, "suspended_at": None}]},
            "/user/installations/34/repositories": {"total_count": 1, "repositories": [self.repo]},
        }
        self.requests = []

    def verify(self):
        def send(request):
            self.requests.append(request)
            self.assertEqual(request.url.host, "api.github.com")
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.headers["authorization"], "Bearer synthetic_user_token")
            body = self.responses[request.url.path]
            return body if isinstance(body, httpx.Response) else httpx.Response(200, json=body)

        with httpx.Client(transport=httpx.MockTransport(send), follow_redirects=True) as client:
            return check_requester(client, user_token="synthetic_user_token", actor_id=12, app_id=56,
                                   installation_id=34, repository_id=78)

    def test_exact_verified_actor_and_repo(self):
        self.assertEqual(self.verify(), Standing(12, 56, 34, 78))
        self.assertEqual([r.url.path for r in self.requests], list(self.responses))

    def test_redirect_is_not_followed_even_if_client_enables_redirects(self):
        self.responses["/user"] = httpx.Response(302, headers={"location": "https://example.invalid/"})
        self.assertIsNone(self.verify())
        self.assertEqual(len(self.requests), 1)

    def test_revocation_or_read_only_does_not_reuse_prior_success(self):
        self.assertIsNotNone(self.verify())
        self.repo["permissions"]["admin"] = False
        self.assertIsNone(self.verify())
        self.responses["/user"] = httpx.Response(401)
        self.assertIsNone(self.verify())

    def test_incomplete_or_inconsistent_records_fail_closed(self):
        self.responses["/user/installations/34/repositories"]["total_count"] = 2
        self.assertIsNone(self.verify())
        self.responses["/user/installations/34/repositories"]["repositories"].append(self.repo)
        self.assertIsNone(self.verify())

    def test_wrong_account_does_not_request_installation(self):
        self.responses["/user"] = {"id": 99, "type": "User"}
        self.assertIsNone(self.verify())
        self.assertEqual(len(self.requests), 1)

    def test_suspended_installation_stops_before_list_repositories(self):
        self.responses["/user/installations"]["installations"][0]["suspended_at"] = "fixture"
        self.assertIsNone(self.verify())
        self.assertEqual(len(self.requests), 2)
