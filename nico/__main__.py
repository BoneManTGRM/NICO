import sys

from nico.cli import main as cli_main
from nico.no_server_assessment import main as assess_main


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "assess":
        assess_main(sys.argv[2:])
    else:
        cli_main()
