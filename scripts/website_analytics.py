"""Collect bounded website analytics using gcloud and free BigQuery table reads."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError

PROJECT = "www-fmind-dev"
TABLE = f"{PROJECT}.website_analytics.run_googleapis_com_stderr"
ENDPOINT = f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/datasets/website_analytics/tables/run_googleapis_com_stderr"
PAYLOAD_FIELDS = ("msg", "path", "status", "bot", "referer", "utm_source", "utm_medium", "utm_campaign")
SELECTION = ",".join(("timestamp", "insertId", *(f"jsonPayload.{name}" for name in PAYLOAD_FIELDS)))
MAX_ROWS = 100_000
MAX_BYTES = 64 * 1024 * 1024


class AnalyticsError(RuntimeError):
    """Evidence could not be collected completely and safely."""


class SchemaField(BaseModel):
    """Projected BigQuery field, in the server's response order."""

    name: str
    type: str
    fields: list[SchemaField] = Field(default_factory=list)


class Schema(BaseModel):
    fields: list[SchemaField]


class Metadata(BaseModel):
    table_schema: Schema = Field(alias="schema")
    num_rows: str = Field(alias="numRows")
    last_modified_time: str = Field(alias="lastModifiedTime")


class Cell(BaseModel):
    v: str | Row | None


class Row(BaseModel):
    f: list[Cell]


class Page(BaseModel):
    rows: list[Row] = Field(default_factory=list)
    total_rows: str = Field(alias="totalRows")
    page_token: str = Field(default="", alias="pageToken")


class Event(BaseModel):
    """Only the allowlisted analytics dimensions enter aggregation."""

    model_config = ConfigDict(strict=True)
    timestamp: datetime
    insert_id: str | None
    path: str
    status: int = Field(ge=100, le=599)
    bot: bool | None
    referer: str
    utm_source: str
    utm_medium: str
    utm_campaign: str


def gcloud(*arguments: str) -> str:
    """Capture tokens and diagnostics; never echo command output on failure."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed executable, separate argv; no shell.
            ["gcloud", *arguments, "--quiet"],  # noqa: S607 - resolved through the pinned workstation PATH.
            check=True,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AnalyticsError("gcloud failed; check the installed CLI and existing account authorization.") from exc
    return result.stdout.strip()


def access_token() -> str:
    """Resolve existing identity without inheriting a different quota project."""
    overrides = (
        "CLOUDSDK_AUTH_ACCESS_TOKEN",
        "CLOUDSDK_AUTH_ACCESS_TOKEN_FILE",
        "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE",
        "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT",
    )
    if any(os.environ.get(name) for name in overrides):
        raise AnalyticsError(
            "Credential override present; review the effective gcloud identity before reading analytics."
        )
    configuration = gcloud("config", "configurations", "list", "--filter=is_active:true", "--format=value(name)")
    if not configuration or "\n" in configuration:
        raise AnalyticsError("Expected one active gcloud configuration.")
    context = [f"--configuration={configuration}", f"--project={PROJECT}", f"--billing-project={PROJECT}"]
    for name in ("auth/impersonate_service_account", "auth/access_token_file", "auth/credential_file_override"):
        if gcloud(*context, "config", "get", name) not in ("", "(unset)"):
            raise AnalyticsError(
                "Credential override configured; review the effective gcloud identity before reading analytics."
            )
    account = gcloud(*context, "config", "get", "account")
    if not account or account == "(unset)":
        raise AnalyticsError("No gcloud account selected; authorize the intended account before retrying.")
    token = gcloud(*context, f"--account={account}", "auth", "print-access-token")
    if not token:
        raise AnalyticsError("gcloud returned no access token.")
    return token


@dataclass(repr=False)
class Reader:
    """GET-only client with fixed destination and bounded in-memory responses."""

    token: str
    downloaded: int = 0

    def __call__(self, suffix: str, parameters: dict[str, str]) -> bytes:
        request = Request(  # noqa: S310 - fixed first-party HTTPS endpoint.
            ENDPOINT + suffix + "?" + urlencode(parameters),
            headers={"Authorization": f"Bearer {self.token}", "x-goog-user-project": PROJECT},
            method="GET",
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed first-party HTTPS endpoint.
                body = response.read(MAX_BYTES - self.downloaded + 1)
        except HTTPError as exc:
            exc.close()
            raise AnalyticsError(
                f"BigQuery HTTP {exc.code}; check table existence and read permissions. No report produced."
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise AnalyticsError("BigQuery read timed out or failed; no partial report produced.") from exc
        self.downloaded += len(body)
        if self.downloaded > MAX_BYTES:
            raise AnalyticsError("Analytics exceeds the 64 MiB read cap; no partial report produced.")
        return body


def decode_event(row: Row, fields: list[SchemaField]) -> Event:
    """Decode positional REST values against the projected live schema."""
    values = {field.name: cell.v for field, cell in zip(fields, row.f, strict=True)}
    payload = values["jsonPayload"]
    payload_fields = next(field.fields for field in fields if field.name == "jsonPayload")
    if not isinstance(payload, Row):
        raise AnalyticsError("Analytics payload missing.")
    dimensions = {field.name: cell.v for field, cell in zip(payload_fields, payload.f, strict=True)}
    if dimensions["msg"] != "analytics_pageview":
        raise AnalyticsError("Unexpected event in the analytics-only table.")
    raw_bot = dimensions["bot"]
    if raw_bot not in ("true", "false", None):
        raise AnalyticsError("Invalid bot flag in analytics data.")
    raw_status, raw_timestamp = dimensions["status"], values["timestamp"]
    if not isinstance(raw_status, str) or not isinstance(raw_timestamp, str):
        raise AnalyticsError("Missing status or timestamp in analytics data.")
    status = Decimal(raw_status)
    if not status.is_finite() or status != status.to_integral_value():
        raise AnalyticsError("Invalid HTTP status in analytics data.")
    return Event.model_validate(
        {
            "timestamp": datetime.fromtimestamp(float(raw_timestamp), UTC),
            "insert_id": values["insertId"],
            "status": int(status),
            "bot": None if raw_bot is None else raw_bot == "true",
            **{name: dimensions[name] for name in ("path", "referer", "utm_source", "utm_medium", "utm_campaign")},
        }
    )


def collect(read: Callable[[str, dict[str, str]], bytes]) -> tuple[list[Event], int]:
    """Require all pages and stable metadata; a truncated read is never a sample."""
    parameters: dict[str, str] = {"selectedFields": SELECTION}
    before = Metadata.model_validate_json(read("", parameters))
    fields = before.table_schema.fields
    if {field.name for field in fields} != {"timestamp", "insertId", "jsonPayload"}:
        raise AnalyticsError("Analytics table schema changed.")
    payload = next(field for field in fields if field.name == "jsonPayload")
    if {field.name for field in payload.fields} != set(PAYLOAD_FIELDS):
        raise AnalyticsError("Analytics payload schema changed.")
    expected = int(before.num_rows)
    if not 0 <= expected <= MAX_ROWS:
        raise AnalyticsError("Analytics exceeds the 100,000 row cap; no partial report produced.")
    events: list[Event] = []
    seen: set[tuple[datetime, str]] = set()
    duplicates = 0
    raw_count = 0
    page_token = ""
    for _ in range(100):
        page = Page.model_validate_json(read("/data", {**parameters, "maxResults": "10000", "pageToken": page_token}))
        raw_count += len(page.rows)
        if int(page.total_rows) != expected or raw_count > expected:
            raise AnalyticsError("Analytics table changed during the read; retry once when ingestion is settled.")
        for row in page.rows:
            event = decode_event(row, fields)
            if event.insert_id:
                key = (event.timestamp, event.insert_id)
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)
            events.append(event)
        if not page.page_token:
            break
        if page.page_token == page_token:
            raise AnalyticsError("Repeated analytics page token; no partial report produced.")
        page_token = page.page_token
    else:
        raise AnalyticsError("Analytics exceeds the 100 page cap; no partial report produced.")
    after = Metadata.model_validate_json(read("", parameters))
    if raw_count != expected or before != after:
        raise AnalyticsError("Analytics read incomplete or table changed; retry once when ingestion is settled.")
    return events, duplicates


def successful(event: Event) -> bool:
    return event.bot is False and 200 <= event.status < 300


def breakdown(events: list[Event], start: date, days: int, zone: ZoneInfo) -> dict[str, object]:
    """Aggregate one complete calendar window with explicit denominators."""
    views = [event for event in events if successful(event)]
    daily = Counter(event.timestamp.astimezone(zone).date().isoformat() for event in views)
    event_days = {event.timestamp.astimezone(zone).date() for event in events}
    referrers: Counter[str] = Counter()
    campaigns: Counter[tuple[str, str, str]] = Counter()
    for event in views:
        host = event.referer.lower()
        referrers["same-site" if host in ("www.fmind.dev", "fmind.dev") else host or "direct / unknown"] += 1
        if event.utm_source or event.utm_medium or event.utm_campaign:
            campaigns[(event.utm_source, event.utm_medium, event.utm_campaign)] += 1
    bots = sum(event.bot is True for event in events)
    return {
        "html_events": len(events),
        "successful_non_bot_views": len(views),
        "daily_average": round(len(views) / days, 2),
        "bot_events": bots,
        "bot_share_percent": round(100 * bots / len(events), 2) if events else None,
        "unknown_bot_events": sum(event.bot is None for event in events),
        "html_4xx": sum(400 <= event.status < 500 for event in events),
        "html_5xx": sum(event.status >= 500 for event in events),
        "non_bot_4xx": sum(event.bot is False and 400 <= event.status < 500 for event in events),
        "non_bot_5xx": sum(event.bot is False and event.status >= 500 for event in events),
        "daily_views": {
            (start + timedelta(days=i)).isoformat(): daily[(start + timedelta(days=i)).isoformat()] for i in range(days)
        },
        "zero_event_dates": [
            (start + timedelta(days=i)).isoformat() for i in range(days) if start + timedelta(days=i) not in event_days
        ],
        "top_pages": dict(Counter(event.path for event in views).most_common(10)),
        "referrers": dict(referrers.most_common(10)),
        "tagged_views": sum(campaigns.values()),
        "campaigns": [
            {"source": source, "medium": medium, "campaign": campaign, "views": count}
            for (source, medium, campaign), count in campaigns.most_common(10)
        ],
    }


def summarize(events: list[Event], *, end: date, days: int, zone: ZoneInfo, duplicates: int = 0) -> dict[str, object]:
    """Compare adjacent complete local-date windows; do not assume human identity."""
    start = end - timedelta(days=days)
    previous_start = start - timedelta(days=days)

    def boundary(day: date) -> datetime:
        return datetime.combine(day, time.min, zone).astimezone(UTC)

    current = [event for event in events if boundary(start) <= event.timestamp < boundary(end)]
    previous = [event for event in events if boundary(previous_start) <= event.timestamp < boundary(start)]
    current_pages = Counter(event.path for event in current if successful(event))
    previous_pages = Counter(event.path for event in previous if successful(event))
    paths = sorted(
        current_pages.keys() | previous_pages.keys(),
        key=lambda path: (-abs(current_pages[path] - previous_pages[path]), path),
    )
    changes = [
        {
            "path": path,
            "current": current_pages[path],
            "previous": previous_pages[path],
            "change": current_pages[path] - previous_pages[path],
        }
        for path in paths[:10]
    ]
    first = min((event.timestamp for event in events), default=None)
    return {
        "source": TABLE,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "timezone": zone.key,
        "start_inclusive": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "previous_start_inclusive": previous_start.isoformat(),
        "retained_events_read": len(events),
        "duplicates_excluded": duplicates,
        "first_retained_event": first.isoformat() if first else None,
        "latest_retained_event": max(event.timestamp for event in events).isoformat() if events else None,
        "history_starts_after_comparison_start": first is None or first > boundary(previous_start),
        "current": breakdown(current, start, days, zone),
        "previous": breakdown(previous, previous_start, days, zone),
        "largest_page_changes": changes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, choices=range(1, 91), default=7, metavar="1..90")
    parser.add_argument("--end-date", type=date.fromisoformat, help="Exclusive local date; default: today")
    parser.add_argument("--timezone", default="Europe/Paris")
    args = parser.parse_args(argv)
    try:
        zone = ZoneInfo(args.timezone)
        today = datetime.now(zone).date()
        end = args.end_date or today
        if end > today or end - timedelta(days=2 * args.days) < today - timedelta(days=180):
            raise AnalyticsError("Both complete reporting windows must be within the last 180 days.")
        events, duplicates = collect(Reader(access_token()))
        report = summarize(events, end=end, days=args.days, zone=zone, duplicates=duplicates)
    except (
        AnalyticsError,
        ValueError,
        KeyError,
        OverflowError,
        InvalidOperation,
        ValidationError,
        ZoneInfoNotFoundError,
    ) as exc:
        message = (
            str(exc)
            if isinstance(exc, AnalyticsError)
            else "Invalid analytics schema, date, or timezone; no report produced."
        )
        sys.stderr.write(f"website-analytics: {message}\n")
        return 1
    sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
