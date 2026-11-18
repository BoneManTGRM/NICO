import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import qualify_postgres as q


class StartupCleanup(unittest.TestCase):
    def test_partial_start_failure_attempts_stop_and_retains_primary_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = pathlib.Path(tmp)
            for name in ('initdb','pg_ctl','psql'):
                (binary/name).write_bytes(b'synthetic-not-executable')
            calls = []
            def run(args, **kwargs):
                args = [str(x) for x in args]
                calls.append(args)
                if args[-1] == 'start':
                    raise RuntimeError('synthetic_start_failed')
                if args[-1] == 'stop':
                    raise RuntimeError('synthetic_cleanup_failed')
                return subprocess.CompletedProcess(args, 0, stdout=b'synthetic_version')
            created = []
            original = q.tempfile.mkdtemp
            def allocate(**kwargs):
                path = original(dir=tmp, **kwargs)
                created.append(pathlib.Path(path))
                return path
            with patch.object(q,'BIN',binary), patch.object(q,'run',run), \
                 patch.dict(q.os.environ, {'GITHUB_ACTIONS':'true'}), \
                 patch.object(q.tempfile,'mkdtemp',allocate):
                with self.assertRaisesRegex(RuntimeError, '^synthetic_start_failed$'):
                    q.qualify()
            self.assertTrue(any(x[-1]=='stop' for x in calls))
            self.assertTrue(created[0].exists())
            self.assertFalse((created[0]/'safe-to-remove').exists())

    def test_clean_fixture_directory_removed(self):
        with q.fixture_directory() as root:
            self.assertTrue(root.exists())
        self.assertFalse(root.exists())

    def test_non_github_invocation_fails_before_process(self):
        with patch.dict(q.os.environ, {}, clear=True), patch.object(q,'run') as run:
            with self.assertRaisesRegex(ValueError, '^synthetic_github_runner_required$'):
                q.qualify()
            run.assert_not_called()
