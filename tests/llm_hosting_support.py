"""Shared helper for the LLM self-hosting calculator tests."""

from datetime import UTC, datetime

from www.sites.calculator import build_llm_self_hosting_view
from www.sites.inputs import Query
from www.sites.models import LLMSelfHostingView

# A fixed date before every API price review and expiry date, so views do not depend on the clock.
NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


def view(query: Query | None = None) -> LLMSelfHostingView:
    """Build the advanced-mode calculator view at the fixed test date."""
    return build_llm_self_hosting_view({"mode": "advanced", **(query or {})}, now=NOW)
