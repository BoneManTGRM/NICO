"""Exact #1917 primitives on the existing synthetic loopback fixture only."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Barrier
from uuid import uuid4

FIXTURE = "postgresql://nico:nico@127.0.0.1:5432/nico"
RUN = "comprun_" + "1" * 32
from nico.self_serve_candidate import bilingual_seal, oauth_state, oauth_state_store, sealed_readback, run_identity


def pin_sources():
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, timeout=5).decode().strip()
    if os.environ.get("GITHUB_ACTIONS") == "true" and revision != os.environ.get("GITHUB_SHA"):
        raise RuntimeError("candidate_checkout_revision_mismatch")
    for module in (bilingual_seal, oauth_state, oauth_state_store, sealed_readback, run_identity):
        path = Path(module.__file__).resolve()
        relative = path.relative_to(root).as_posix()
        original = subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=root, timeout=5)
        if path.read_bytes() != original:
            raise RuntimeError("candidate_source_not_checked_out_revision")
    return revision


def connect(schema):
    import psycopg
    return psycopg.connect(FIXTURE, hostaddr="127.0.0.1", sslmode="disable",
                           connect_timeout=3, options=f"-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000")


def fixture():
    test = [("en", b"%PDF-synthetic-english"), ("es-MX", b"%PDF-synthetic-spanish")]
    return tuple(bilingual_seal.RetainedEdition(lang, sealed_readback.SealedPdf(sha256(raw).hexdigest(), len(raw)), raw)
                 for lang, raw in test)


def readback(schema):
    with connect(schema) as conn, conn.cursor() as cursor:
        for edition in fixture():
            observed = bilingual_seal.read_edition(cursor, dialect="postgres", run_id=RUN, revision=2,
                                                  locale=edition.locale, expected=edition.binding)
            if observed != edition.content:
                raise RuntimeError("independent_exact_readback_failed")
        print("independent bilingual exact-byte readback passed")


class Proof(unittest.TestCase):
    def setUp(self):
        self.schema = "nico_1917_proof_" + uuid4().hex
        with connect(self.schema) as conn:
            conn.execute("CREATE SCHEMA " + self.schema)
            conn.execute(oauth_state_store.POSTGRES_SCHEMA)
            conn.execute(bilingual_seal.POSTGRES_SCHEMA)

    def test_bilingual_rollback_restart_readback_and_duplicate(self):
        def stage(conn):
            with conn.cursor() as c:
                bilingual_seal.stage_bilingual(c, dialect="postgres", run_id=RUN, revision=2, editions=fixture())
        with connect(self.schema) as conn:
            stage(conn)
            conn.rollback()
        with connect(self.schema) as conn:
            count = conn.execute("SELECT count(*) FROM nico_self_serve_retained_editions").fetchone()[0]
            self.assertEqual(count, 0)
            stage(conn)
        import psycopg
        with self.assertRaises(psycopg.errors.UniqueViolation), connect(self.schema) as conn:
            stage(conn)
        self.assertEqual(subprocess.run([sys.executable, __file__, "--read", self.schema], timeout=15,
                                        text=True, capture_output=True, check=True).stdout.strip(),
                         "independent bilingual exact-byte readback passed")

    def test_state_single_transaction_winner(self):
        def flow(clock):
            store = oauth_state_store.SqlOAuthStateStore(lambda: connect(self.schema), dialect="postgres")
            return oauth_state.GithubAppFlow(store, configured_redirect="https://nico.example/oauth/callback", clock=clock)
        actor = "a" * 43
        pending = flow(lambda: 100).begin(trusted_browser_binding=actor)
        def consume(f, browser):
            return f.consume(state=pending["state"], trusted_browser_binding=browser)
        self.assertIsNone(consume(flow(lambda: 101), "b" * 43))
        barrier = Barrier(2)
        def compete(_):
            barrier.wait(timeout=5)
            return consume(flow(lambda: 102), actor)
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(value is not None for value in pool.map(compete, range(2))), 1)
        self.assertIsNone(consume(flow(lambda: 103), actor))


if __name__ == "__main__":
    revision = pin_sources()
    if sys.argv[1:] == ["--check-source"]:
        print(f"Exact source verified at {revision}; PostgreSQL not exercised")
    elif (os.environ.get("NICO_1917_SYNTHETIC_POSTGRES") != "1"
          or os.environ.get("NICO_TEST_DATABASE_URL") != FIXTURE):
        raise SystemExit("Select the existing loopback synthetic fixture explicitly; no connection attempted")
    elif len(sys.argv) == 3 and sys.argv[1] == "--read":
        import re
        if not re.fullmatch(r"nico_1917_proof_[0-9a-f]{32}", sys.argv[2]):
            raise SystemExit("Invalid synthetic schema")
        readback(sys.argv[2])
    else:
        unittest.main()
