"""Owned negative controls for verified import bytes; no native/provider work."""
import hashlib
import importlib.util
from pathlib import Path
import py_compile
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

PREPARE = module('owned_prepare_loader_controls', ROOT / 'scripts/cpp_full_static_prepare.py')
SCOPE = module('owned_scope_loader_controls', ROOT / 'scripts/cpp_static_runner_scope.py')

class VerifiedBufferControls(unittest.TestCase):
    def test_captured_verified_bytes_survive_source_replacement_and_stale_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'library.py'
            path.write_text('raise RuntimeError("untrusted_cached_module")\n')
            py_compile.compile(str(path), doraise=True)
            verified = b'identity = "verified"\n'
            loader = PREPARE._VerifiedBufferLoader('owned_verified', path, verified)
            path.write_text('raise RuntimeError("untrusted_replaced_module")\n')
            target = types.ModuleType('owned_verified')
            loader.exec_module(target)
            self.assertEqual(target.identity, 'verified')
            with self.assertRaises(OSError):
                loader.get_data(importlib.util.cache_from_source(str(path)))

    def test_direct_scope_loader_uses_actual_module_name_and_rejects_changed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'library.py';raw = b'identity = "owned"\n'
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            target = types.ModuleType('owned_candidate_compiler')
            SCOPE.VerifiedLoader(path, digest, target.__name__).exec_module(target)
            self.assertEqual(target.identity, 'owned')
            compatible = SCOPE.VerifiedLoader(path, digest)
            compatible.name = target.__name__
            compatible.exec_module(target)
            self.assertEqual(target.identity, 'owned')
            path.write_text('identity = "changed"\n')
            with self.assertRaises(ValueError):
                SCOPE.VerifiedLoader(path, digest, target.__name__).exec_module(target)


if __name__ == '__main__':
    unittest.main()
