"""Application entry composition for Mini Redis REPL."""

from __future__ import annotations

import sys

from mini_redis.cli import run_repl
from mini_redis.store import Store


def main(argv: list[str] | None = None) -> int:
    """Run Mini Redis REPL and return process exit code."""
    del argv
    store = Store()
    return run_repl(store, sys.stdin, sys.stderr, sys.stdout)
