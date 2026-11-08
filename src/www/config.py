"""Typed environment configuration parsed once at process startup."""

import ipaddress
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

# Google Cloud project IDs: 6-30 lowercase letters, digits, or hyphens, starting with a letter.
_PROJECT_ID = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]")


class Environment(StrEnum):
    """Supported runtime modes."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


@dataclass(frozen=True, slots=True)
class Config:
    """Validated runtime settings."""

    environment: Environment = Environment.DEVELOPMENT
    # Loopback keeps local runs off the network; the runtime image sets HOST=0.0.0.0 for Cloud Run.
    host: str = "127.0.0.1"
    port: int = 8080
    # Empty outside Cloud Run: logs then omit Cloud Logging's request trace field.
    google_cloud_project: str = ""

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

        host = values.get("HOST", "127.0.0.1")
        try:
            ipaddress.ip_address(host)
        except ValueError as error:
            msg = f"invalid HOST {host!r} (want an IP address such as 127.0.0.1 or 0.0.0.0)"
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

        project = values.get("GOOGLE_CLOUD_PROJECT", "")
        if project and not _PROJECT_ID.fullmatch(project):
            msg = f"invalid GOOGLE_CLOUD_PROJECT {project!r} (want a 6-30 character Google Cloud project ID)"
            raise ValueError(msg)
        return cls(environment=environment, host=host, port=port, google_cloud_project=project)
