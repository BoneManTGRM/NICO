from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest

from nico.self_serve_candidate.bilingual_seal import (
    SQLITE_SCHEMA, RetainedEdition, read_edition, stage_bilingual,
)
from nico.self_serve_candidate.sealed_readback import SealedPdf

RUN = "comprun_" + "a" * 32


def fixture(locale):
    raw = b"%PDF-fixture-" + locale.encode("ascii")
    return RetainedEdition(locale, SealedPdf(sha256(raw).hexdigest(), len(raw)), raw)


class BilingualSealTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "artifact.db"
        with sqlite3.connect(self.path) as conn:
            conn.execute(SQLITE_SCHEMA)
        self.en, self.es = fixture("en"), fixture("es-MX")

    def publish(self, pair, *, fail=False):
        with sqlite3.connect(self.path) as conn:
            stage_bilingual(conn.cursor(), dialect="sqlite", run_id=RUN, revision=3, editions=pair)
            if fail:
                raise RuntimeError("simulated caller rollback")

    def read(self, locale, revision=3, binding=None):
        with sqlite3.connect(self.path) as conn:
            return read_edition(conn.cursor(), dialect="sqlite", run_id=RUN, revision=revision,
                                locale=locale, expected=binding or fixture(locale).binding)

    def test_exact_bilingual_bytes_survive_connection_close(self):
        self.publish((self.es, self.en))
        self.assertEqual(self.read("en"), self.en.content)
        self.assertEqual(self.read("es-MX"), self.es.content)

    def test_duplicate_publication_does_not_replace_the_original(self):
        self.publish((self.en, self.es))
        with self.assertRaises(sqlite3.IntegrityError):
            self.publish((self.en, self.es))
        self.assertEqual(self.read("en"), self.en.content)

    def test_invalid_second_edition_writes_nothing(self):
        with self.assertRaises(ValueError):
            self.publish((self.en, replace(self.es, content=self.en.content)))
        self.assertIsNone(self.read("en"))

    def test_caller_owned_rollback_cancels_both(self):
        with self.assertRaisesRegex(RuntimeError, "caller rollback"):
            self.publish((self.en, self.es), fail=True)
        self.assertIsNone(self.read("en"))
        self.assertIsNone(self.read("es-MX"))

    def test_wrong_revision_or_expected_binding_never_serves_bytes(self):
        self.publish((self.en, self.es))
        self.assertIsNone(self.read("en", revision=2))
        self.assertIsNone(self.read("en", binding=self.es.binding))
