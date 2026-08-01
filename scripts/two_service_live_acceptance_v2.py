from __future__ import annotations

import sys

import two_service_live_acceptance_v2_retry_wrapper as _wrapper


for _name, _value in vars(_wrapper).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


if __name__ == "__main__":
    try:
        raise SystemExit(_wrapper.main())
    except ValueError as exc:
        print(f"Configuration blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
