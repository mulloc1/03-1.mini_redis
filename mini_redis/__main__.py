"""python -m mini_redis module entrypoint."""

from __future__ import annotations

import sys

from mini_redis.main import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
