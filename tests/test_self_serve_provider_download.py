from dataclasses import replace
from hashlib import sha256
import unittest

import httpx

from nico.self_serve_candidate.download_binding import DownloadSnapshot, DownloadUnavailable, Edition, Grant, Principal
from nico.self_serve_candidate.provider_download import RepositoryScope, VerifiedSession, download_for_requester
from nico.self_serve_candidate.sealed_readback import SealedPdf


class FakeStore:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.reads = 0

    def read_active(self, principal, edition):
        self.reads += 1
        return self.snapshot


class PrivateRead(unittest.TestCase):
    def setUp(self):
        self.locale = Edition("comprun_" + "2" * 32, "es-MX")
        self.session = VerifiedSession(12, "synthetic_user_token")
        self.scope = RepositoryScope(78, 34, 56)
        self.raw = b"%PDF-synthetic-es"
        seal = SealedPdf(sha256(self.raw).hexdigest(), len(self.raw))
        grant = Grant(Principal("https://github.com", "12"), self.locale, "78", "a"*40, seal)
        self.store = FakeStore(DownloadSnapshot(grant, "78", "a"*40, True, self.raw))
        self.active = True

    def read(self):
        def response(request):
            if request.url.path == "/user":
                return (httpx.Response(200,json={"id":12,"type":"User"})
                        if self.active else httpx.Response(401))
            if request.url.path == "/user/installations":
                return httpx.Response(200,json={"total_count":1, "installations":[
                    {"id":34,"app_id":56,"suspended_at":None}]})
            assert request.url.path == "/user/installations/34/repositories"
            return httpx.Response(200,json={"total_count":1,"repositories":[
                {"id":78,"owner":{"id":12,"type":"User"},"permissions":{"pull":True}}]})

        with httpx.Client(transport=httpx.MockTransport(response)) as client:
            return download_for_requester(client, session=self.session, scope=self.scope,
                                          edition=self.locale, store=self.store)

    def test_returns_original_bytes_without_shared_cache(self):
        download = self.read()
        self.assertEqual(download.content, self.raw)
        self.assertIn("no-store", download.headers["Cache-Control"])

    def test_revocation_cannot_read_after_warm_success(self):
        self.read()
        self.active = False
        with self.assertRaises(DownloadUnavailable):
            self.read()
        self.assertEqual(self.store.reads, 1)

    def test_repository_mismatch_denies_even_after_provider_success(self):
        self.store.snapshot = replace(self.store.snapshot, repository_id="79")
        with self.assertRaises(DownloadUnavailable):
            self.read()

    def test_wrong_grant_recipient_denied(self):
        grant = replace(self.store.snapshot.grant, recipient=Principal("https://github.com","19"))
        self.store.snapshot = replace(self.store.snapshot, grant=grant)
        with self.assertRaises(DownloadUnavailable):
            self.read()

    def test_other_locale_or_changed_bytes_denied(self):
        for snapshot in (replace(self.store.snapshot, pdf_bytes=b"%PDF-synthetic-en"),
                         replace(self.store.snapshot, grant=replace(self.store.snapshot.grant,
                                 edition=replace(self.locale, locale="en")))):
            self.store.snapshot = snapshot
            with self.assertRaises(DownloadUnavailable):
                self.read()
