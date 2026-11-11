"""Observable report semantics and bounded cloud-read failures."""

import http.client
import json
import ssl
import subprocess
from datetime import UTC, date, datetime, timedelta, tzinfo
from email.message import Message
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

import pytest

from scripts import website_analytics as analytics


def event(
    when: str, *, path: str = "/", bot: bool | None = False, status: int = 200, **dimensions: str
) -> analytics.Event:
    return analytics.Event(
        timestamp=datetime.fromisoformat(when),
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
    assert current["burst_events"] == 0
    assert current["burst_paths"] == {}
    assert current["unknown_bot_events"] == 1
    assert current["html_4xx"] == 1
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


def test_per_path_bursts_are_excluded_from_human_views_and_4xx() -> None:
    base = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    minute_burst = [
        analytics.Event(
            timestamp=base + timedelta(seconds=second),
            path="/sites/llm-self-hosting/",
            status=200,
            bot=False,
            referer="www.fmind.dev",
            utm_source="",
            utm_medium="",
            utm_campaign="",
        )
        for second in range(21)
    ]
    hour_burst = [
        analytics.Event(
            timestamp=base + timedelta(hours=1, seconds=59 * index),
            path="/404",
            status=404,
            bot=False,
            referer="",
            utm_source="",
            utm_medium="",
            utm_campaign="",
        )
        for index in range(61)
    ]
    calm = [
        analytics.Event(
            timestamp=base + timedelta(hours=2, seconds=index),
            path="/launch/",
            status=200,
            bot=False,
            referer="news.ycombinator.com",
            utm_source="",
            utm_medium="",
            utm_campaign="",
        )
        for index in range(20)
    ]
    report = analytics.summarize(
        [*minute_burst, *hour_burst, *calm],
        end=date(2026, 9, 16),
        days=7,
        zone=ZoneInfo("Europe/Paris"),
    )
    current = report["current"]
    assert isinstance(current, dict)
    assert current["successful_non_bot_views"] == 20
    assert current["burst_events"] == 82
    assert current["burst_paths"] == {"/404": 61, "/sites/llm-self-hosting/": 21}
    assert current["non_bot_4xx"] == 0
    assert current["top_pages"] == {"/launch/": 20}
    assert report["largest_page_changes"] == [
        {"path": "/launch/", "current": 20, "previous": 0, "change": 20},
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


def metadata(
    rows: int = 2,
    modified: str = "1",
    *,
    extra: tuple[str, ...] = (),
    payload: tuple[str, ...] = analytics.PAYLOAD_FIELDS,
) -> bytes:
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
                        "fields": [{"name": name, "type": "STRING"} for name in payload],
                    },
                    *({"name": name, "type": "STRING"} for name in extra),
                ]
            },
        }
    ).encode()


def wire_row(
    identifier: str = "event-1",
    status: str | None = "200.0",
    bot: str | None = "false",
    *,
    msg: str = "analytics_pageview",
    payload: bool = True,
) -> dict[str, object]:
    dimensions = {"f": [{"v": value} for value in (msg, "/", status, bot, "", "", "", "")]}
    return {"f": [{"v": identifier}, {"v": "1789000000.5"}, {"v": dimensions if payload else "flattened"}]}


class FakeRead:
    def __init__(self, *responses: bytes) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, suffix: str, parameters: dict[str, str]) -> bytes:
        self.calls.append((suffix, parameters))
        return next(self.responses)


def page(*rows: dict[str, object], total: int = 2, cursor: str = "") -> bytes:
    return json.dumps({"rows": rows, "totalRows": str(total), "pageToken": cursor}).encode()


DAY = (date(2026, 9, 9),)


def test_pagination_schema_order_and_duplicate_events() -> None:
    read = FakeRead(metadata(), page(wire_row(), cursor="next-page"), page(wire_row()), metadata())
    events, duplicates = analytics.collect(read, DAY)
    assert len(events) == 1
    assert duplicates == 1
    assert events[0].status == 200
    assert events[0].timestamp == datetime.fromtimestamp(1789000000.5, UTC)
    assert [suffix for suffix, _ in read.calls] == ["$20260909", "$20260909/data", "$20260909/data", "$20260909"]
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
        ((metadata(analytics.MAX_ROWS + 1),), "row cap"),
        ((metadata(), page(wire_row(), total=3)), "changed"),
        ((metadata(), page(wire_row()), metadata()), "incomplete"),
        ((metadata(1), page(wire_row(), total=1), metadata(1, modified="2")), "changed"),
        ((metadata(), page(cursor="same"), page(cursor="same")), "Repeated"),
        ((metadata(), page(wire_row(status="200.5"))), "Invalid HTTP status"),
        ((metadata(), page(wire_row(bot="unknown"))), "Invalid bot flag"),
        ((metadata(extra=("severity",)),), "table schema changed"),
        ((metadata(payload=analytics.PAYLOAD_FIELDS[:-1]),), "payload schema changed"),
        ((metadata(), page(wire_row(msg="http_request"))), "Unexpected event"),
        ((metadata(), page(wire_row(status=None))), "Missing status"),
        ((metadata(), page(wire_row(payload=False))), "payload missing"),
        ((metadata(0), metadata(1)), "changed"),
    ],
)
def test_incomplete_or_invalid_reads_fail_without_reporting(responses: tuple[bytes, ...], message: str) -> None:
    with pytest.raises(analytics.AnalyticsError, match=message):
        analytics.collect(FakeRead(*responses), DAY)


def test_reads_only_the_requested_partitions_and_skips_empty_ones() -> None:
    days = (date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10))
    read = FakeRead(
        metadata(1),
        metadata(0),
        metadata(1),
        page(wire_row("first"), total=1),
        metadata(1),
        metadata(0),
        page(wire_row("first"), total=1),
        metadata(1),
    )
    events, duplicates = analytics.collect(read, days)
    # The same insertId in two partitions is two events: a duplicate shares its timestamp, hence its partition.
    assert (len(events), duplicates) == (2, 0)
    assert [suffix for suffix, _ in read.calls] == [
        "$20260908",
        "$20260909",
        "$20260910",
        "$20260908/data",
        "$20260908",
        "$20260909",
        "$20260910/data",
        "$20260910",
    ]


def test_row_cap_applies_to_the_sum_of_partitions_before_any_data_read() -> None:
    read = FakeRead(metadata(analytics.MAX_ROWS), metadata(1))
    with pytest.raises(analytics.AnalyticsError, match="row cap"):
        analytics.collect(read, (date(2026, 9, 8), date(2026, 9, 9)))
    assert [suffix for suffix, _ in read.calls] == ["$20260908", "$20260909"]


def test_page_cap_spans_partitions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analytics, "MAX_PAGES", 1)
    read = FakeRead(metadata(1), metadata(1), page(wire_row("a"), total=1), metadata(1))
    with pytest.raises(analytics.AnalyticsError, match="page cap"):
        analytics.collect(read, (date(2026, 9, 8), date(2026, 9, 9)))


@pytest.mark.parametrize(
    ("zone", "end", "expected"),
    [
        # Paris midnight is 22:00 or 23:00 UTC the day before: the window never reaches the end date's partition.
        ("Europe/Paris", date(2026, 11, 8), (date(2026, 11, 5), date(2026, 11, 7))),
        ("Europe/Paris", date(2026, 7, 1), (date(2026, 6, 28), date(2026, 6, 30))),
        ("UTC", date(2026, 11, 8), (date(2026, 11, 6), date(2026, 11, 7))),
        # West of UTC, local midnight falls inside the end date's UTC day, so that partition is required.
        ("America/New_York", date(2026, 11, 8), (date(2026, 11, 6), date(2026, 11, 8))),
    ],
)
def test_partitions_cover_both_local_windows_in_utc_days(zone: str, end: date, expected: tuple[date, date]) -> None:
    tz = ZoneInfo(zone)
    days = analytics.partitions(analytics.boundary(end - timedelta(days=2), tz), analytics.boundary(end, tz))
    assert (days[0], days[-1]) == expected
    assert days == [expected[0] + timedelta(days=offset) for offset in range(len(days))]


def test_main_reads_the_partitions_of_both_windows_and_the_day_before(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    requested: list[list[date]] = []

    def collect(_read: object, days: list[date]) -> tuple[list[analytics.Event], int]:
        requested.append(days)
        # Full retained history: every partition holds traffic at noon UTC.
        return [event(f"{day.isoformat()}T12:00:00+00:00") for day in days], 0

    monkeypatch.setattr(analytics, "access_token", lambda: "secret-token")
    monkeypatch.setattr(analytics, "collect", collect)
    end = datetime.now(UTC).date() - timedelta(days=2)
    assert analytics.main(["--days", "7", "--end-date", end.isoformat(), "--timezone", "UTC"]) == 0
    # A UTC window starts on a partition boundary; the preceding day shows whether history predates it.
    assert requested == [[end - timedelta(days=15 - offset) for offset in range(15)]]
    assert json.loads(capsys.readouterr().out)["history_starts_after_comparison_start"] is False


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
    with pytest.raises(analytics.AnalyticsError, match="3 GiB read cap"):
        analytics.Reader("secret-token", downloaded=analytics.MAX_BYTES - 10)("$20260909/data", {})


@pytest.mark.parametrize(
    "failure",
    [
        URLError("name resolution failed"),
        TimeoutError("read timed out"),
        ConnectionResetError("connection reset by peer"),
        ssl.SSLError("bad record mac"),
        http.client.IncompleteRead(b"partial"),
    ],
    ids=("url", "timeout", "reset", "tls", "incomplete"),
)
def test_reader_network_failures_stay_inside_the_error_contract(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], failure: Exception
) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def read(self, _size: int) -> bytes:
            raise failure

    monkeypatch.setattr(analytics, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(analytics.AnalyticsError, match="timed out or failed") as error:
        analytics.Reader("secret-token")("/data", {})
    assert error.value.__cause__ is failure
    assert "secret-token" not in str(error.value)

    monkeypatch.setattr(analytics, "access_token", lambda: "secret-token")
    assert analytics.main(["--timezone", "UTC"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "website-analytics: BigQuery read timed out or failed; no partial report produced.\n"


@pytest.mark.parametrize(
    ("responses", "message"),
    [
        ([""], "one active gcloud configuration"),
        (["default\nother"], "one active gcloud configuration"),
        (["default", "reader@example.test"], "Credential override configured"),
        (["default", "(unset)", "", "/private/token-file"], "Credential override configured"),
        (["default", "(unset)", "", "", "(unset)"], "No gcloud account"),
        (["default", "(unset)", "", "", "owner@example.test", ""], "no access token"),
    ],
    ids=("no-configuration", "many-configurations", "impersonation", "token-file", "no-account", "empty-token"),
)
def test_auth_fails_closed_on_ambiguous_gcloud_identity(
    monkeypatch: pytest.MonkeyPatch, responses: list[str], message: str
) -> None:
    for name in (
        "CLOUDSDK_AUTH_ACCESS_TOKEN",
        "CLOUDSDK_AUTH_ACCESS_TOKEN_FILE",
        "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE",
        "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT",
    ):
        monkeypatch.delenv(name, raising=False)
    answers = iter(responses)
    monkeypatch.setattr(analytics, "gcloud", lambda *_args: next(answers))
    with pytest.raises(analytics.AnalyticsError, match=message):
        analytics.access_token()


@pytest.mark.parametrize(
    ("days", "end_offset", "allowed"),
    [(90, 0, True), (90, 1, False), (89, 2, True), (7, -1, False)],
    ids=("oldest-window", "beyond-retention", "inside-retention", "future-end"),
)
def test_main_keeps_both_windows_inside_retention_before_authenticating(
    monkeypatch: pytest.MonkeyPatch, days: int, end_offset: int, allowed: bool
) -> None:
    class FrozenDatetime(datetime):
        """Pin main's clock, so the window checks cannot straddle a UTC midnight."""

        @classmethod
        def now(cls, tz: tzinfo | None = None) -> FrozenDatetime:
            return cls(2026, 11, 8, 23, 59, 59, 999999, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(analytics, "datetime", FrozenDatetime)
    today = date(2026, 11, 8)
    authenticated: list[bool] = []

    def token() -> str:
        authenticated.append(True)
        return "secret-token"

    monkeypatch.setattr(analytics, "access_token", token)
    monkeypatch.setattr(analytics, "collect", lambda _read, _days: ([], 0))
    end = (today - timedelta(days=end_offset)).isoformat()
    status = analytics.main(["--days", str(days), "--end-date", end, "--timezone", "UTC"])
    assert (status, authenticated) == ((0, [True]) if allowed else (1, []))


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
    monkeypatch.setattr(analytics, "collect", lambda _read, _days: ([], 0))
    assert analytics.main([]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["retained_events_read"] == 0
    assert "secret-token" not in output.out
    assert analytics.main(["--timezone", "Invalid/Zone"]) == 1
    assert capsys.readouterr().out == ""
