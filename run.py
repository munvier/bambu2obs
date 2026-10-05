"""Launcher used to build the standalone executable (see README)."""

import sys
import traceback

from bambu2obs.__main__ import main


def run() -> int:
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 1
    # When double-clicked, the console closes on exit: keep errors readable.
    if code != 0 and getattr(sys, "frozen", False):
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass
    return code


if __name__ == "__main__":
    sys.exit(run())
