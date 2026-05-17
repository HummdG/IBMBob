"""Allow `python -m gitbob ...` as an alternative to the `gitbob` script."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
