"""Release-owned scheduling estimates, never evidence of test execution.

The ASan suites taking at least 25 seconds in retained run 36250553285 receive
their measured millisecond costs. See docs/evidence/pr1644-sanitizer-ordering/.
CTest's documented COST property orders existing tests without selecting them.
"""

ADDRESS_COSTS_MS = {
    'cluster_linearize_tests': 203529,
    'checkqueue_tests': 147685,
    'coins_tests_dbbase': 147382,
    'coinselector_tests': 121812,
    'coins_tests_base': 80516,
    'random_tests': 77950,
    'miniscript_tests': 62799,
    'chain_tests': 51010,
    'secp256k1.tests.ecmult_multi_tests': 50646,
    'txrequest_tests': 45744,
    'net_tests': 43442,
    'secp256k1.noverify_tests.ecmult_multi_tests': 42094,
    'coins_tests': 32045,
    'txvalidationcache_tests': 31605,
    'transaction_tests': 31493,
    'wallet_tests': 27355,
}

# Historical runtime plans retain their exact old logging program. This new
# wrapper changes only generated build metadata, never target source or results.
SCHEDULE_LOG_EXEC_PROGRAM = r'''
import hashlib, json, os, re, stat, sys

def schedule_costs(costs, *, root='/work'):
    if (not isinstance(costs, dict) or not 1 <= len(costs) <= 64
            or any(not isinstance(name, str) or re.fullmatch(r'[A-Za-z0-9_.]+', name) is None
                   or type(cost) is not int or not 1 <= cost <= 300000
                   for name, cost in costs.items())):
        raise ValueError('worker_runtime_schedule_invalid')
    marker = b'# NICO retained-address-cost-v1 scheduling estimates only\n'
    addition = b'\n' + marker + ''.join(
        'set_tests_properties(' + name + ' PROPERTIES COST ' + str(cost) + ')\n'
        for name, cost in sorted(costs.items())).encode('ascii')
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        directory = os.open('sanitize-address', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent)
        try:
            fd = os.open('CTestTestfile.cmake', os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= 1048576:
                    raise ValueError('worker_runtime_schedule_invalid')
                original = os.read(fd, 1048577)
                if len(original) != info.st_size or marker in original:
                    raise ValueError('worker_runtime_schedule_invalid')
                remaining = addition
                while remaining:
                    written = os.write(fd, remaining)
                    if written <= 0: raise ValueError('worker_runtime_schedule_invalid')
                    remaining = remaining[written:]
                return {'policy': 'retained-address-cost-v1', 'costs_ms': costs,
                        'original_sha256': hashlib.sha256(original).hexdigest(),
                        'scheduled_sha256': hashlib.sha256(original + addition).hexdigest()}
            finally:
                os.close(fd)
        finally:
            os.close(directory)
    finally:
        os.close(parent)

if __name__ == '__main__':
    log_path, raw_costs, argv = sys.argv[1], sys.argv[2], sys.argv[3:]
    if (log_path != '/work/sanitize-address/nico-runtime-ctest.log'
            or not argv or argv[:3] != ['ctest', '--test-dir', '/work/sanitize-address']):
        raise SystemExit(2)
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    os.dup2(fd, 1); os.dup2(fd, 2)
    if fd > 2: os.close(fd)
    print(json.dumps(schedule_costs(json.loads(raw_costs)), sort_keys=True), flush=True)
    os.execvp(argv[0], argv)
'''
