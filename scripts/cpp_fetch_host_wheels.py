"""Fetch only the five reviewed public wheels; installation is a separate step."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

MAX_MANIFEST = 65536
MAX_WHEEL = 8 * 1024 * 1024


def require(ok, code):
    if not ok:
        raise ValueError(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('wheel_redirect_rejected')


def public_url(url, filename):
    value = urllib.parse.urlsplit(url)
    require(value.scheme == 'https' and value.netloc == 'files.pythonhosted.org'
            and not value.query and not value.fragment and not value.username
            and value.path.startswith('/packages/')
            and value.path.rsplit('/', 1)[-1] == filename, 'wheel_url')
    require(type(filename) is str and re.fullmatch(r'[A-Za-z0-9_.-]+\.whl', filename),
            'wheel_filename')
    return url


def manifest_rows(raw, expected):
    require(len(raw) <= MAX_MANIFEST and hashlib.sha256(raw).hexdigest() == expected,
            'reviewed_manifest_digest')
    value = json.loads(raw)
    require(value['schema'] == 'nico.diagnostic.cp311-host-wheels.v1', 'manifest_schema')
    rows = value['wheels']
    require(type(rows) is list and len(rows) == 5
            and len({r['name'] for r in rows}) == 5
            and len({r['filename'] for r in rows}) == 5, 'wheel_population')
    for row in rows:
        public_url(row['url'], row['filename'])
        require(type(row['bytes']) is int and 0 < row['bytes'] <= MAX_WHEEL
                and type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']),
                'wheel_pin')
    return rows


def verified_body(raw, row):
    require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
            'wheel_digest_or_size')
    return raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = args.manifest.absolute()
    require(manifest.resolve(strict=True) == manifest and manifest.is_file(), 'manifest_path')
    with manifest.open('rb') as stream:
        rows = manifest_rows(stream.read(MAX_MANIFEST + 1), args.manifest_sha256)
    output = args.output.absolute()
    require(output.parent.resolve(strict=True) == output.parent and not output.exists(), 'new_output')
    os.umask(0o077)
    output.mkdir(mode=0o700)
    opener = urllib.request.build_opener(NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    for row in rows:
        req = urllib.request.Request(row['url'], headers={'Accept': 'application/octet-stream'})
        with opener.open(req, timeout=30) as response:
            require(response.status == 200 and response.url == row['url'], 'wheel_response')
            raw = verified_body(response.read(row['bytes'] + 1), row)
        with (output / row['filename']).open('xb') as stream:
            stream.write(raw)
    print('{"status":"REVIEWED_PUBLIC_WHEELS_RETAINED","installed":false}')


if __name__ == '__main__':
    main()
