import sys

from .cli import parse, run_cli


def main() -> int:
    args, _rest = parse(sys.argv[1:])
    code = run_cli(args)
    return code if code is not None else 0


if __name__ == "__main__":
    sys.exit(main())
