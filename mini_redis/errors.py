"""Domain exceptions for Mini Redis (CLI maps these to Redis-style errors)."""


class CommandError(Exception):
    """Raised for invalid commands, arity, or argument parsing (CLI phase)."""


class OOMError(Exception):
    """Raised when a single key+value exceeds maxmemory (Phase 3)."""
