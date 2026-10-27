"""Run directly with Python/unittest: no application or pytest bootstrap needed."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('owned_worker_environment', Path(__file__).with_name('owned_worker_environment.py'))
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class OwnedWorkerEnvironmentTest(unittest.TestCase):
    def test_only_runtime_allowlist_and_owned_storage_reach_child(self):
        modules_before = set(sys.modules)
        parent = {'PATH':'/owned/bin', 'LANG':'C.UTF-8', 'PYTHONPATH':'/owned/dependencies',
                  **{key:'adversarial-synthetic-value' for key in (
                      'DATABASE_URL', 'NICO_DATABASE_URL', 'NICO_HOME', 'NICO_SQLITE_PATH',
                      'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN',
                      'AWS_PROFILE', 'AWS_SHARED_CREDENTIALS_FILE', 'GOOGLE_APPLICATION_CREDENTIALS',
                      'AZURE_STORAGE_CONNECTION_STRING', 'NICO_STORAGE_BUCKET', 'S3_ENDPOINT_URL',
                      'RAILWAY_TOKEN', 'GITHUB_TOKEN', 'PYTHONSTARTUP', 'HOME')}}
        original = dict(parent)
        with tempfile.TemporaryDirectory() as owned:
            environment = helper.owned_worker_environment(Path('/owned/repository'), Path(owned), parent)
            self.assertEqual(set(environment), {'PATH','LANG','PYTHONPATH','PYTHONNOUSERSITE','NICO_HOME','NICO_SQLITE_PATH'})
            self.assertEqual(environment['NICO_HOME'], owned)
            self.assertEqual(environment['NICO_SQLITE_PATH'], str(Path(owned)/'nico.sqlite3'))
            self.assertFalse(any(value=='adversarial-synthetic-value' for value in environment.values()))
        self.assertEqual(parent, original)
        self.assertFalse(any(name.startswith('nico.api') for name in set(sys.modules) - modules_before))

    def test_missing_parent_runtime_variables_do_not_add_configuration(self):
        environment = helper.owned_worker_environment(Path('/owned/repository'),Path('/owned/tmp'),{})
        self.assertEqual(set(environment), {'PYTHONPATH','PYTHONNOUSERSITE','NICO_HOME','NICO_SQLITE_PATH'})


if __name__ == '__main__':
    unittest.main()
