"""Bounded owned GCC/Clang/Cap'n Proto link controls; no assessed source."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

GXX = '/usr/local/bin/g++'
CLANG = '/usr/lib/llvm-17/bin/clang'
CLANGXX = '/usr/lib/llvm-17/bin/clang++'
LIBRARIES = ['/usr/local/lib/libcapnpc.a', '/usr/local/lib/libcapnp.a',
             '/usr/local/lib/libkj.a']
SOURCE = r'''
#include <capnp/message.h>
#include <capnp/schema-parser.h>
#include <cstddef>
#include <cstdint>
static int owned_control() {
    capnp::SchemaParser parser;
    capnp::MallocMessageBuilder message;
    return 0;
}
#ifdef NICO_FUZZ_CONTROL
extern "C" int LLVMFuzzerTestOneInput(const uint8_t*, size_t) {
    return owned_control();
}
#else
int main() { return owned_control(); }
#endif
'''


def verify(*, run=subprocess.run) -> dict:
    receipt = {'schema': 'nico.cpp-runtime-toolchain-control.v1',
               'status': 'UNPROVEN', 'assessed_source_executed': False,
               'native_qualification_completed': False, 'commands': [],
               'source_sha256': hashlib.sha256(SOURCE.encode()).hexdigest()}

    def execute(argv, *, expected_failure=False, stdin=None):
        result = run(argv, input=stdin, text=True, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, timeout=20, check=False)
        receipt['commands'].append({'argv': argv, 'exit_code': result.returncode,
                                    'stdout': result.stdout, 'stderr': result.stderr})
        if expected_failure:
            if result.returncode == 0 or 'undefined reference to' not in result.stderr or '__cxa_call_terminate' not in result.stderr:
                raise ValueError('old_runtime_link_failure_not_reproduced')
        elif result.returncode != 0:
            raise ValueError('toolchain_control_command_failed')
        return result.stdout.strip()

    try:
        if execute([GXX, '-dumpfullversion']) != '14.2.0':
            raise ValueError('gcc_version_mismatch')
        if execute([CLANGXX, '-dumpversion']) != '17.0.6':
            raise ValueError('clang_version_mismatch')
        for filename in ('libgcc.a', 'libstdc++.so'):
            expected = Path(execute([GXX, '-print-file-name=' + filename])).resolve(strict=True)
            actual = Path(execute([CLANGXX, '-print-file-name=' + filename])).resolve(strict=True)
            if expected != actual or not expected.is_relative_to('/usr/local'):
                raise ValueError('clang_gcc_runtime_mismatch')
        macros = execute([CLANGXX, '-dM', '-E', '-x', 'c++', '-'],
                         stdin='#include <bits/c++config.h>\n')
        if '#define _GLIBCXX_RELEASE 14' not in macros.splitlines():
            raise ValueError('clang_gcc_headers_mismatch')
        with tempfile.TemporaryDirectory(prefix='nico-owned-link-') as directory:
            root = Path(directory)
            source = root / 'owned.cpp'
            source.write_text(SOURCE)
            obj = str(root / 'owned.o')
            execute([CLANGXX, '-std=c++20', '-c', str(source), '-o', obj])
            # Same object and static archives, with only runtime discovery changed.
            execute([CLANGXX, '--no-default-config', obj, *LIBRARIES, '-pthread',
                     '-o', str(root / 'old-runtime')], expected_failure=True)
            executable = str(root / 'owned')
            execute([CLANGXX, obj, *LIBRARIES, '-pthread', '-o', executable])
            execute([executable])
            fuzz = str(root / 'owned-fuzz')
            execute([CLANGXX, '-std=c++20', '-DNICO_FUZZ_CONTROL',
                     '-fsanitize=address,fuzzer,undefined', str(source),
                     *LIBRARIES, '-pthread', '-o', fuzz])
            execute([fuzz, '-runs=1'])
        receipt['status'] = 'VERIFIED_OWNED_TOOLCHAIN'
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        receipt['error'] = str(exc)
    return receipt


if __name__ == '__main__':
    result = verify()
    print(json.dumps(result, sort_keys=True, indent=2))
    raise SystemExit(0 if result['status'] == 'VERIFIED_OWNED_TOOLCHAIN' else 1)
