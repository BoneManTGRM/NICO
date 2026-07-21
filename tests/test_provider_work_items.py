from __future__ import annotations

import httpx

from nico.provider_credentials import EnvironmentCredentialResolver, build_reference
from nico.provider_live_clients import RetryPolicy
from nico.provider_work_items import AzureBoardsClient, adapt_bitbucket_issues, adapt_gitlab_issues


def _azure_credential():
    reference = build_reference(
        provider="azure_devops",
        env_var="AZURE_TOKEN",
        scheme="basic_token",
        key_id="azure-boards-test",
        allowed_hosts=("dev.azure.com",),
        scopes=("vso.work",),
    )
    return EnvironmentCredentialResolver({"AZURE_TOKEN": "secret"}).resolve(reference)


def test_gitlab_and_bitbucket_issue_adapters_are_canonical() -> None:
    gitlab = adapt_gitlab_issues(
        [
            {
                "iid": 7,
                "title": "Repair issue",
                "state": "opened",
                "assignee": {"username": "dev"},
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
                "web_url": "https://gitlab.example.com/issues/7",
            }
        ],
        project_id="group",
        repository_id="17",
    )
    bitbucket = adapt_bitbucket_issues(
        [
            {
                "id": 9,
                "kind": "bug",
                "title": "Fix bug",
                "state": "new",
                "assignee": {"display_name": "Developer"},
                "created_on": "2026-01-01T00:00:00Z",
                "updated_on": "2026-01-02T00:00:00Z",
                "links": {"html": {"href": "https://bitbucket.example.com/issues/9"}},
            }
        ],
        project_id="workspace",
        repository_id="repo-uuid",
    )

    assert gitlab[0].native_id == "7"
    assert gitlab[0].assignee == "dev"
    assert gitlab[0].source_fingerprint.startswith("sha256:")
    assert bitbucket[0].item_type == "bug"
    assert bitbucket[0].repository_id == "repo-uuid"
    assert bitbucket[0].source_fingerprint.startswith("sha256:")


def test_azure_boards_queries_and_batches_work_items() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.headers["Authorization"].startswith("Basic ")
        if request.url.path.endswith("/_apis/wit/wiql"):
            return httpx.Response(200, json={"workItems": [{"id": 1}, {"id": 2}]})
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": 1,
                        "url": "https://dev.azure.com/Org/Project/_apis/wit/workItems/1",
                        "fields": {
                            "System.WorkItemType": "Bug",
                            "System.Title": "Critical bug",
                            "System.State": "Active",
                            "System.AssignedTo": {"displayName": "Developer"},
                            "System.CreatedDate": "2026-01-01T00:00:00Z",
                            "System.ChangedDate": "2026-01-02T00:00:00Z",
                        },
                    },
                    {
                        "id": 2,
                        "fields": {
                            "System.WorkItemType": "User Story",
                            "System.Title": "Add capability",
                            "System.State": "New",
                            "System.CreatedDate": "2026-01-01T00:00:00Z",
                            "System.ChangedDate": "2026-01-03T00:00:00Z",
                        },
                    },
                ]
            },
        )

    client = AzureBoardsClient(
        organization="Org",
        project="Project",
        credential=_azure_credential(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
    )
    result = client.collect(repository_id="azure-repo")

    assert result.provider.value == "azure_devops"
    assert result.project_id == "Project"
    assert result.repository_id == "azure-repo"
    assert len(result.items) == 2
    assert result.items[0].item_type == "bug"
    assert result.items[0].assignee == "Developer"
    assert result.items[1].state == "new"
    assert result.requests_made == 2
    assert result.pages_fetched == 2
    assert len(requests) == 2


def test_azure_boards_empty_query_is_valid_complete_evidence() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"workItems": []})

    client = AzureBoardsClient(
        organization="Org",
        project="Project",
        credential=_azure_credential(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
    )
    result = client.collect(repository_id="azure-repo")
    assert result.items == ()
    assert result.requests_made == 1
    assert result.pages_fetched == 1
