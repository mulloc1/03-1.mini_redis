"""CLI parser, dispatcher, and REPL loop for Mini Redis."""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, TextIO

from mini_redis.errors import CommandError, OOMError
from mini_redis.store import Store, StoreMetrics

PROMPT: Final[str] = "mini-redis> "

ERR_UNKNOWN_COMMAND: Final[str] = "ERR unknown command '{cmd}'"
ERR_WRONG_ARITY: Final[str] = "ERR wrong number of arguments for '{cmd}' command"
ERR_INVALID_INTEGER: Final[str] = "ERR value is not an integer or out of range"
ERR_OOM: Final[str] = "OOM command not allowed when used_memory > 'maxmemory'"
ERR_CONFIG_SUBCOMMAND: Final[str] = (
    "ERR unknown subcommand or wrong number of arguments for 'set'"
)
ERR_UNBALANCED_QUOTES: Final[str] = "ERR unbalanced quotes in request"

EXIT_SIGNAL: Final[object] = object()


def _tokenize(line: str) -> list[str]:
    """Split *line* by whitespace with support for double-quoted tokens."""
    tokens: list[str] = []
    i = 0
    n = len(line)

    while i < n:
        while i < n and line[i].isspace():
            i += 1
        if i >= n:
            break
        if line[i] == '"':
            i += 1
            start = i
            while i < n and line[i] != '"':
                i += 1
            if i >= n:
                raise CommandError(ERR_UNBALANCED_QUOTES)
            tokens.append(line[start:i])
            i += 1
            continue
        start = i
        while i < n and not line[i].isspace():
            i += 1
        tokens.append(line[start:i])

    return tokens


def _fmt_ok() -> str:
    """Return Redis-style success token."""
    return "OK"


def _fmt_nil() -> str:
    """Return Redis-style nil token."""
    return "(nil)"


def _fmt_integer(n: int) -> str:
    """Return Redis-style integer wrapper."""
    return f"(integer) {n}"


def _fmt_bulk(value: str) -> str:
    """Return Redis-style quoted string value."""
    return f'"{value}"'


def _fmt_keys(keys: list[str]) -> str:
    """Return Redis-style KEYS output with index labels."""
    if not keys:
        return "(empty array)"
    lines = [f'{index}) "{key}"' for index, key in enumerate(keys, start=1)]
    return "\n".join(lines)


def _fmt_info_memory(metrics: StoreMetrics) -> str:
    """Return INFO memory lines."""
    return (
        f"used_memory:{metrics.used_memory}\n"
        f"maxmemory:{metrics.maxmemory}\n"
        f"evicted_keys:{metrics.evicted_keys}"
    )


def _fmt_error(message: str) -> str:
    """Return Redis-style error wrapper."""
    return f"(error) {message}"


def _parse_int(token: str) -> int:
    """Parse integer token or raise CommandError with Redis text."""
    try:
        return int(token)
    except ValueError as exc:
        raise CommandError(ERR_INVALID_INTEGER) from exc


def _h_set(store: Store, args: list[str]) -> str:
    """Handle SET key value."""
    store.set(args[0], args[1])
    return _fmt_ok()


def _h_get(store: Store, args: list[str]) -> str:
    """Handle GET key."""
    value = store.get(args[0])
    if value is None:
        return _fmt_nil()
    return _fmt_bulk(value)


def _h_del(store: Store, args: list[str]) -> str:
    """Handle DEL key."""
    return _fmt_integer(store.delete(args[0]))


def _h_exists(store: Store, args: list[str]) -> str:
    """Handle EXISTS key."""
    return _fmt_integer(store.exists(args[0]))


def _h_dbsize(store: Store, args: list[str]) -> str:
    """Handle DBSIZE."""
    del args
    return _fmt_integer(store.dbsize())


def _h_keys(store: Store, args: list[str]) -> str:
    """Handle KEYS."""
    del args
    return _fmt_keys(store.keys())


def _h_expire(store: Store, args: list[str]) -> str:
    """Handle EXPIRE key seconds."""
    seconds = _parse_int(args[1])
    return _fmt_integer(store.expire(args[0], seconds))


def _h_ttl(store: Store, args: list[str]) -> str:
    """Handle TTL key."""
    return _fmt_integer(store.ttl(args[0]))


def _h_config(store: Store, args: list[str]) -> str:
    """Handle CONFIG SET maxmemory bytes."""
    if len(args) != 3:
        raise CommandError(ERR_CONFIG_SUBCOMMAND)
    if args[0].upper() != "SET" or args[1].lower() != "maxmemory":
        raise CommandError(ERR_CONFIG_SUBCOMMAND)
    value = _parse_int(args[2])
    try:
        store.set_maxmemory(value)
    except ValueError as exc:
        raise CommandError(ERR_INVALID_INTEGER) from exc
    return _fmt_ok()


def _h_info(store: Store, args: list[str]) -> str:
    """Handle INFO memory."""
    if len(args) != 1 or args[0].lower() != "memory":
        raise CommandError(ERR_CONFIG_SUBCOMMAND)
    return _fmt_info_memory(store.info_memory())


Handler = Callable[[Store, list[str]], str]
_DISPATCH: Final[dict[str, tuple[Handler, int]]] = {
    "SET": (_h_set, 2),
    "GET": (_h_get, 1),
    "DEL": (_h_del, 1),
    "EXISTS": (_h_exists, 1),
    "DBSIZE": (_h_dbsize, 0),
    "KEYS": (_h_keys, 0),
    "EXPIRE": (_h_expire, 2),
    "TTL": (_h_ttl, 1),
    "CONFIG": (_h_config, -1),
    "INFO": (_h_info, -1),
}


def dispatch(store: Store, line: str) -> str | object | None:
    """Dispatch a single command line to Store and format result text."""
    try:
        tokens = _tokenize(line)
        if not tokens:
            return None

        command_raw = tokens[0]
        if command_raw.lower() in {"exit", "quit"}:
            return EXIT_SIGNAL

        command = command_raw.upper()
        route = _DISPATCH.get(command)
        if route is None:
            return _fmt_error(ERR_UNKNOWN_COMMAND.format(cmd=command_raw))

        handler, expected_arity = route
        args = tokens[1:]
        if expected_arity >= 0 and len(args) != expected_arity:
            return _fmt_error(ERR_WRONG_ARITY.format(cmd=command.lower()))
        return handler(store, args)
    except OOMError:
        return _fmt_error(ERR_OOM)
    except CommandError as exc:
        return _fmt_error(str(exc))


def run_repl(
    store: Store,
    stdin: TextIO,
    stderr: TextIO,
    stdout: TextIO,
) -> int:
    """Run the REPL loop and return process exit code."""
    while True:
        stderr.write(PROMPT)
        stderr.flush()
        line = stdin.readline()
        if line == "":
            return 0
        result = dispatch(store, line.strip())
        if result is EXIT_SIGNAL:
            return 0
        if isinstance(result, str):
            stdout.write(f"{result}\n")
            stdout.flush()
