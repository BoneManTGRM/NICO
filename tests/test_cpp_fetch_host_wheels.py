"""Inert transport guards; never fetch, install or execute a wheel."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/cpp_fetch_host_wheels.py'
spec = importlib.util.spec_from_file_location('wheel_fetch_controls', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WheelTransportControls(unittest.TestCase):
    def test_official_exact_url(self):
        url = 'https://files.pythonhosted.org/packages/aa/input-1-py3-none-any.whl'
        self.assertEqual(module.public_url(url, 'input-1-py3-none-any.whl'), url)

    def test_untrusted_destination_credentials_query_scheme(self):
        for url in ('http://files.pythonhosted.org/packages/a/a.whl',
                    'https://evil.example/packages/a/a.whl',
                    'https://files.pythonhosted.org.evil.example/packages/a/a.whl',
                    'https://user:secret@files.pythonhosted.org/packages/a/a.whl',
                    'https://files.pythonhosted.org/packages/a/a.whl?key=x',
                    'https://files.pythonhosted.org/packages/a/a.whl#x',
                    'https://files.pythonhosted.org/packages/a/other.whl'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                module.public_url(url, 'a.whl')

    def test_redirect_rejected_before_follow(self):
        with self.assertRaisesRegex(ValueError, 'wheel_redirect_rejected'):
            module.NoRedirect().redirect_request(None, None, 302, None, {}, 'https://evil.example')

    def test_digest_and_length_required(self):
        body = b'exact wheel input'
        row = {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
        self.assertEqual(module.verified_body(body, row), body)
        for changed in (body[:-1], body + b'x', b'x' * len(body)):
            with self.assertRaises(ValueError):
                module.verified_body(changed, row)

    def test_manifest_anchor_and_population(self):
        rows = [{'name': str(i), 'filename': str(i) + '.whl',
                 'url': 'https://files.pythonhosted.org/packages/a/' + str(i) + '.whl',
                 'sha256': '0' * 64, 'bytes': 1} for i in range(5)]
        value = {'schema': 'nico.diagnostic.cp311-host-wheels.v1', 'wheels': rows}
        raw = json.dumps(value).encode()
        self.assertEqual(len(module.manifest_rows(raw, hashlib.sha256(raw).hexdigest())), 5)
        with self.assertRaises(ValueError):
            module.manifest_rows(raw, 'f' * 64)
        value['wheels'][-1] = value['wheels'][0]
        raw = json.dumps(value).encode()
        with self.assertRaises(ValueError):
            module.manifest_rows(raw, hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    unittest.main()
