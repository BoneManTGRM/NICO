"""Bounded staging of the single pinned native-test asset; no assessed execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

URL = 'https://github.com/bitcoin-core/qa-assets/raw/b33d85102d169b54d966ea315ad81a636680aefa/unit_test_data/script_assets_test.json'
EXPECTED_BYTES = 9243520
EXPECTED_SHA256 = 'cd789a58ec45916e1721cdd14e82ca4c93100959f1cef4e229b22e3bf539f095'
TRANSIENT_HTTP = {'408', '429', '500', '502', '503', '504'}


def stage(destination, *, run=subprocess.run, clock=time.monotonic, pause=time.sleep):
    destination = Path(destination)
    deadline = clock() + 90
    with tempfile.TemporaryDirectory(prefix='.unit-asset-', dir=destination.parent) as private:
        partial = Path(private) / 'download.part'
        for attempt in range(4):
            partial.unlink(missing_ok=True)
            seconds = min(20, int(deadline - clock()) - 1)
            if seconds < 1:
                raise ValueError('asset_download_deadline')
            argv = ['curl', '--disable', '--location', '--fail', '--silent', '--show-error', '--connect-timeout', '5',
                    '--max-time', str(seconds), '--max-filesize', str(EXPECTED_BYTES),
                    '--output', str(partial), '--write-out', '%{http_code}', URL]
            try:
                result = run(argv, capture_output=True, text=True, timeout=seconds + 1, check=False)
                status = result.stdout.strip()
                transient = result.returncode == 28 or (result.returncode == 22 and status in TRANSIENT_HTTP)
            except subprocess.TimeoutExpired:
                transient = True
                result = None
            if clock() >= deadline:
                raise ValueError('asset_download_deadline')
            if result is not None and result.returncode == 0 and status == '200':
                # The private transfer must be a regular file, never a link or
                # special file. Read at most one byte beyond the pinned size.
                fd = os.open(partial, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, 'rb') as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode):
                        raise ValueError('asset_download_file_invalid')
                    raw = stream.read(EXPECTED_BYTES + 1)
                if len(raw) != EXPECTED_BYTES:
                    raise ValueError('asset_download_size_invalid')
                if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
                    raise ValueError('asset_download_hash_invalid')
                # Publish the bytes just verified, not a transfer path that
                # could have changed since the read.
                verified = Path(private) / 'verified'
                with verified.open('xb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                if clock() >= deadline:
                    raise ValueError('asset_download_deadline')
                # Atomic exclusive publication; never replace an existing asset.
                os.link(verified, destination)
                return
            if not transient or attempt == 3:
                raise ValueError('asset_download_failed')
            delay = 2 ** (attempt + 1)
            if clock() + delay + 2 >= deadline:
                raise ValueError('asset_download_deadline')
            pause(delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        stage(args.destination)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        allowed = {'asset_download_deadline', 'asset_download_failed',
                   'asset_download_size_invalid', 'asset_download_hash_invalid',
                   'asset_download_file_invalid'}
        code = str(exc) if str(exc) in allowed else 'asset_download_failed'
        print(json.dumps({'status': 'UNPROVEN', 'error': code}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
