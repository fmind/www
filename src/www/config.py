"""Typed environment configuration parsed once at process startup."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Environment(StrEnum):
    """Supported runtime modes."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


@dataclass(frozen=True, slots=True)
class Config:
    """Validated runtime settings."""

    environment: Environment = Environment.DEVELOPMENT
    port: int = 8080

    @classmethod
    def load(cls, environ: Mapping[str, str] | None = None) -> Config:
        """Parse external configuration and fail before the server starts."""
        values = os.environ if environ is None else environ
        raw_environment = values.get("ENVIRONMENT", Environment.DEVELOPMENT.value)
        try:
            environment = Environment(raw_environment)
        except ValueError as error:
            allowed = ", ".join(repr(item.value) for item in Environment)
            msg = f"invalid ENVIRONMENT {raw_environment!r} (want {allowed})"
            raise ValueError(msg) from error

        raw_port = values.get("PORT", "8080")
        try:
            port = int(raw_port)
        except ValueError as error:
            msg = f"invalid PORT {raw_port!r} (want an integer from 1 through 65535)"
            raise ValueError(msg) from error
        if not 1 <= port <= 65535:
            msg = f"invalid PORT {port} (want 1-65535)"
            raise ValueError(msg)
        return cls(environment=environment, port=port)
