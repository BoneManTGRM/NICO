from __future__ import annotations

import sys

from nico.cli_entrypoint import main as cli_main
from nico.no_server_assessment import main as assess_main


def main() -> None:
    """Dispatch the installed `nico` command and `python -m nico` identically."""

    if len(sys.argv) > 1 and sys.argv[1] == "assess":
        assess_main(sys.argv[2:])
        return
    cli_main()


if __name__ == "__main__":
    main()
