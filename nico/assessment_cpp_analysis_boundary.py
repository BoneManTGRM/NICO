"""Private analyzer artifacts are inaccessible to assessed uid-1000 processes.

These are fixed trusted byte-transfer programs, not project entry points. They
run as unprivileged uid 1001; the assessed build/test programs never use it.
"""
from __future__ import annotations

ANALYSIS_USER = '1001:1001'
ANALYSIS_DIRECTORY = '/work/analysis'
ANALYSIS_SETUP_PROGRAM = r'''
import json, os, pathlib, stat
if os.getuid() != 1001 or os.getgid() != 1001:
    raise ValueError('analysis_identity')
path = pathlib.Path('/work/analysis')
path.mkdir(mode=0o700)
info = path.stat()
if info.st_uid != 1001 or stat.S_IMODE(info.st_mode) != 0o700:
    raise ValueError('analysis_directory')
print(json.dumps({'uid':os.getuid(), 'gid':os.getgid(), 'private':True}))
'''

ANALYSIS_INPUT_PROGRAM = r'''
import base64, hashlib, json, os, pathlib, stat, sys
if os.getuid() != 1001 or os.getgid() != 1001:
    raise ValueError('analysis_identity')
root = pathlib.Path('/work/analysis')
info = root.stat()
if info.st_uid != 1001 or stat.S_IMODE(info.st_mode) != 0o700:
    raise ValueError('analysis_directory')
size = int(sys.argv[1])
raw = sys.stdin.buffer.read(size + 1)
if len(raw) != size:
    raise ValueError('analysis_input_size')
value = json.loads(raw)
data = base64.b64decode(value['data'], validate=True)
if hashlib.sha256(data).hexdigest() != value['sha256']:
    raise ValueError('analysis_input_digest')
with (root / 'compile_commands.json').open('xb') as output:
    output.write(data)
(root / 'compile_commands.json').chmod(0o400)
print(json.dumps({'sha256':hashlib.sha256(data).hexdigest(), 'uid':os.getuid()}))
'''
