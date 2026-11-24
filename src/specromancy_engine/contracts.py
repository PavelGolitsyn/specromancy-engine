"""Small public constants shared across configuration and CLI boundaries."""

from __future__ import annotations


RESPONSE_SCHEMA_VERSION = 2


RESERVED_COMMANDS = frozenset(
    {
        "init",
        "phase",
        "validate",
        "approve",
        "decline",
        "request-approval",
        "block",
        "status",
        "resume",
        "run",
        "adapters",
    }
)

