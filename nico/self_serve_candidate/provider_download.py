"""Offline composition for an existing sealed edition and trusted GitHub session."""
from dataclasses import dataclass, field

import httpx

from .download_binding import DownloadUnavailable, Edition, Principal, private_download
from .github_standing_client import check_requester


@dataclass(frozen=True)
class VerifiedSession:
    # Must be loaded from an authenticated server session; never deserialize one
    # of these objects from browser input. The token is intentionally repr-hidden.
    actor_id: int
    token: str = field(repr=False)


@dataclass(frozen=True)
class RepositoryScope:
    # Loaded from the exact run/grant in trusted storage, not from URL inputs.
    repository_id: int
    installation_id: int
    app_id: int


class _ProviderCheckedStore:
    def __init__(self, client, store, scope, session):
        self._client = client
        self._store = store
        self._scope = scope
        self._session = session

    def read_active(self, principal, edition):
        scope = self._scope
        standing = check_requester(self._client, user_token=self._session.token,
                                   actor_id=self._session.actor_id, app_id=scope.app_id,
                                   installation_id=scope.installation_id,
                                   repository_id=scope.repository_id)
        if standing is None:
            return None
        snapshot = self._store.read_active(principal, edition)
        if snapshot is None or snapshot.repository_id != str(standing.repository_id):
            return None
        return snapshot


def download_for_requester(client: httpx.Client, *, session: VerifiedSession | None,
                           scope: RepositoryScope, edition: Edition, store):
    if type(session) is not VerifiedSession or type(session.actor_id) is not int or session.actor_id <= 0:
        raise DownloadUnavailable()
    # The issuer and numeric provider subject are fixed by the server.
    principal = Principal("https://github.com", str(session.actor_id))
    return private_download(principal, edition,
                            store=_ProviderCheckedStore(client, store, scope, session))
