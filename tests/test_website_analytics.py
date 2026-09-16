"""Observable report semantics and bounded cloud-read failures."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, date, datetime
from email.message import Message
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

import pytest

from scripts import website_analytics as analytics


def event(
    when: str, *, path: str = "/", bot: bool | None = False, status: int = 200, **dimensions: str
) -> analytics.Event:
    return analytics.Event(
        timestamp=datetime.fromisoformat(when),
        insert_id=None,
        path=path,
        status=status,
        bot=bot,
        referer=dimensions.get("referer", ""),
        utm_source=dimensions.get("utm_source", ""),
        utm_medium=dimensions.get("utm_medium", ""),
        utm_campaign=dimensions.get("utm_campaign", ""),
    )


def test_local_midnight_boundaries_bots_errors_and_missing_days() -> None:
    events = [
        event("2026-09-01T22:00:00+00:00", path="/previous"),
        event("2026-09-08T21:59:59+00:00", path="/previous"),
        event("2026-09-08T22:00:00+00:00", path="/current", referer="www.fmind.dev"),
        event("2026-09-15T21:59:59+00:00", path="/current", referer="example.org", utm_source="newsletter"),
        event("2026-09-15T22:00:00+00:00", path="/today"),
        event("2026-09-10T12:00:00+00:00", bot=True),
        event("2026-09-10T12:00:00+00:00", bot=None),
        event("2026-09-10T12:00:00+00:00", path="/404", status=403),
        event("2026-09-10T12:00:00+00:00", path="/500", status=503, bot=True),
    ]
    report = analytics.summarize(events, end=date(2026, 9, 16), days=7, zone=ZoneInfo("Europe/Paris"))
    current = report["current"]
    assert isinstance(current, dict)
    assert current["successful_non_bot_views"] == 2
    assert current["html_events"] == 6
    assert current["bot_events"] == 2
    assert current["unknown_bot_events"] == 1
    assert current["html_4xx"] == 1
    assert current["html_5xx"] == 1
    assert current["non_bot_5xx"] == 0
    assert current["referrers"] == {"same-site": 1, "example.org": 1}
    assert current["tagged_views"] == 1
    assert current["daily_views"] == {
        "2026-09-09": 1,
        "2026-09-10": 0,
        "2026-09-11": 0,
        "2026-09-12": 0,
        "2026-09-13": 0,
        "2026-09-14": 0,
        "2026-09-15": 1,
    }
    assert current["zero_event_dates"] == ["2026-09-11", "2026-09-12", "2026-09-13", "2026-09-14"]
    assert report["largest_page_changes"] == [
        {"path": "/current", "current": 2, "previous": 0, "change": 2},
        {"path": "/previous", "current": 0, "previous": 2, "change": -2},
    ]


def test_dst_comparison_uses_calendar_days_and_empty_history_is_explicit() -> None:
    events = [
        event("2026-03-28T23:00:00+00:00"),  # midnight before the DST jump
        event("2026-03-29T21:59:59+00:00"),  # last second of the 23-hour local day
        event("2026-03-29T22:00:00+00:00"),  # next local day
    ]
    report = analytics.summarize(events, end=date(2026, 3, 30), days=1, zone=ZoneInfo("Europe/Paris"))
    current = report["current"]
    assert isinstance(current, dict)
    assert current["successful_non_bot_views"] == 2
    empty = analytics.summarize([], end=date(2026, 3, 30), days=1, zone=ZoneInfo("UTC"))
    assert empty["history_starts_after_comparison_start"] is True
    assert empty["latest_retained_event"] is None
    previous = empty["previous"]
    assert isinstance(previous, dict)
    assert previous["bot_share_percent"] is None


def metadata(rows: int = 2, modified: str = "1") -> bytes:
    # Deliberately different from selectedFields order: REST follows the schema.
    return json.dumps(
        {
            "numRows": str(rows),
            "lastModifiedTime": modified,
            "schema": {
                "fields": [
                    {"name": "insertId", "type": "STRING"},
                    {"name": "timestamp", "type": "TIMESTAMP"},
                    {
                        "name": "jsonPayload",
                        "type": "RECORD",
                        "fields": [{"name": name, "type": "STRING"} for name in analytics.PAYLOAD_FIELDS],
                    },
                ]
            },
        }
    ).encode()


def wire_row(identifier: str = "event-1", status: str = "200.0", bot: str | None = "false") -> dict[str, object]:
    return {
        "f": [
            {"v": identifier},
            {"v": "1789000000.5"},
            {"v": {"f": [{"v": value} for value in ("analytics_pageview", "/", status, bot, "", "", "", "")]}},
        ]
    }


class FakeRead:
    def __init__(self, *responses: bytes) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, suffix: str, parameters: dict[str, str]) -> bytes:
        self.calls.append((suffix, parameters))
        return next(self.responses)


def page(*rows: dict[str, object], total: int = 2, cursor: str = "") -> bytes:
    return json.dumps({"rows": rows, "totalRows": str(total), "pageToken": cursor}).encode()


def test_pagination_schema_order_and_duplicate_events() -> None:
    read = FakeRead(metadata(), page(wire_row(), cursor="next-page"), page(wire_row()), metadata())
    events, duplicates = analytics.collect(read)
    assert len(events) == 1
    assert duplicates == 1
    assert events[0].status == 200
    assert events[0].timestamp == datetime.fromtimestamp(1789000000.5, UTC)
    assert read.calls[2][1]["pageToken"] == "next-page"
    assert set(read.calls[1][1]["selectedFields"].split(",")) == {
        "timestamp",
        "insertId",
        "jsonPayload.msg",
        "jsonPayload.path",
        "jsonPayload.status",
        "jsonPayload.bot",
        "jsonPayload.referer",
        "jsonPayload.utm_source",
        "jsonPayload.utm_medium",
        "jsonPayload.utm_campaign",
    }


@pytest.mark.parametrize(
    ("responses", "message"),
    [
        ((metadata(100_001),), "row cap"),
        ((metadata(), page(wire_row(), total=3)), "changed"),
        ((metadata(), page(wire_row()), metadata()), "incomplete"),
        ((metadata(1), page(wire_row(), total=1), metadata(1, modified="2")), "changed"),
        ((metadata(), page(cursor="same"), page(cursor="same")), "Repeated"),
        ((metadata(), page(wire_row(status="200.5"))), "Invalid HTTP status"),
        ((metadata(), page(wire_row(bot="unknown"))), "Invalid bot flag"),
    ],
)
def test_incomplete_or_invalid_reads_fail_without_reporting(responses: tuple[bytes, ...], message: str) -> None:
    with pytest.raises(analytics.AnalyticsError, match=message):
        analytics.collect(FakeRead(*responses))


def test_reader_caps_bytes_and_does_not_echo_http_error_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise HTTPError("https://example.test/", 403, "private details", Message(), None)

    monkeypatch.setattr(analytics, "urlopen", denied)
    with pytest.raises(analytics.AnalyticsError, match="HTTP 403") as error:
        analytics.Reader("secret-token")("", {})
    assert "secret-token" not in str(error.value)
    assert "private details" not in str(error.value)

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def read(self, size: int) -> bytes:
            return b"x" * size

    monkeypatch.setattr(analytics, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(analytics.AnalyticsError, match="64 MiB"):
        analytics.Reader("secret-token", downloaded=analytics.MAX_BYTES - 10)("/data", {})


def test_auth_pins_account_and_projects_and_rejects_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    responses = iter(["default", "(unset)", "", "", "owner@example.test", "secret-token"])

    def gcloud(*args: str) -> str:
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(analytics, "gcloud", gcloud)
    assert analytics.access_token() == "secret-token"
    assert {"--account=owner@example.test", "--project=www-fmind-dev", "--billing-project=www-fmind-dev"} <= set(
        calls[-1]
    )
    monkeypatch.setenv("CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT", "other@example.test")
    with pytest.raises(analytics.AnalyticsError, match="Credential override"):
        analytics.access_token()


def test_gcloud_failure_hides_captured_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed(*_args: object, **_kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, "gcloud", output="secret-token", stderr="private details")

    monkeypatch.setattr(analytics.subprocess, "run", failed)
    with pytest.raises(analytics.AnalyticsError) as error:
        analytics.gcloud("auth", "print-access-token")
    assert "secret-token" not in str(error.value)
    assert "private details" not in str(error.value)


def test_main_only_emits_aggregates_and_invalid_timezone_never_authenticates(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(analytics, "access_token", lambda: "secret-token")
    monkeypatch.setattr(analytics, "collect", lambda _read: ([], 0))
    assert analytics.main([]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["retained_events_read"] == 0
    assert "secret-token" not in output.out
    assert analytics.main(["--timezone", "Invalid/Zone"]) == 1
    assert capsys.readouterr().out == ""
