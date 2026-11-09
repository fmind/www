"""Security, request logging, and privacy-preserving analytics middleware."""

import re
import secrets
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

from litestar.datastructures import Headers, MutableScopeHeaders
from litestar.types import ASGIApp, Message, Receive, Scope, Send
from opentelemetry import trace

from www.config import Config, Environment

CANONICAL_APEX = "fmind.dev"
CANONICAL_TARGET = "https://www.fmind.dev"
ANALYTICS_LOG_NAME = "analytics_pageview"

_BOT_TOKENS = (
    "bot",
    "crawler",
    "spider",
    "slurp",
    "bingpreview",
    "facebookexternalhit",
    "linkedinbot",
    # AI assistants fetching on a user's behalf, which omit "bot" from their names.
    "chatgpt-user",
    "claude-user",
    "perplexity-user",
    "meta-externalagent",
    "meta-externalfetcher",
    # Automation and HTTP libraries rather than people.
    "headlesschrome",
    "chrome-lighthouse",
    "curl/",
    "wget/",
    "python-requests",
    "python-httpx",
    "python-urllib",
    "go-http-client",
    "node-fetch",
    "axios/",
    # Link-preview fetchers.
    "preview",
    "whatsapp/",
)

_SILENT_PATHS = frozenset(
    {
        "/health",
        "/favicon.ico",
        "/styles.css",
        "/robots.txt",
        "/sitemap.xml",
        "/site.webmanifest",
        "/llms.txt",
        "/humans.txt",
        "/security.txt",
        "/.well-known/security.txt",
    }
)
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_SAME_ORIGIN_FETCH_SITES = frozenset({"", "same-origin", "none"})
_MCP_PATHS = frozenset({"/mcp", "/mcp/"})
_REPEATED_SLASHES = re.compile(r"/{2,}")
# Cloud Logging joins a log entry to its request log through this special field.
CLOUD_TRACE_LOG_KEY = "logging.googleapis.com/trace"
_TRACEPARENT = re.compile(r"00-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}")
_CLOUD_TRACE_CONTEXT = re.compile(r"([0-9a-f]{32})/[0-9]{1,20}(?:;o=[0-9])?")
_NULL_TRACE_ID = "0" * 32


class Logger(Protocol):
    """The small structured-logging surface the request boundary needs."""

    def info(self, event: str, **values: Any) -> Any: ...

    def error(self, event: str, **values: Any) -> Any: ...


def analytics_path(request_path: str, status: int) -> str:
    """Discard attacker-controlled error paths while retaining their outcome."""
    if status >= 500:
        return "/500"
    if status >= 400:
        return "/404"
    return request_path


def analytics_dimension(value: str) -> str:
    """Accept only short campaign tokens, never arbitrary query text."""
    if len(value) > 128:
        return ""
    allowed = frozenset("._~+-")
    return (
        value
        if all(character.isascii() and (character.isalnum() or character in allowed) for character in value)
        else ""
    )


def referer_host(referer: str) -> str:
    """Reduce a referrer to its lowercase hostname."""
    try:
        parsed = urlsplit(referer)
        return (parsed.hostname or "").lower()
    except ValueError:
        return ""


def is_bot(user_agent: str) -> bool:
    """Classify common crawler user agents without retaining the raw value."""
    normalized = user_agent.strip().lower()
    # Browsers always identify themselves; an empty user agent is a script.
    return not normalized or any(token in normalized for token in _BOT_TOKENS)


def request_trace_id(headers: Headers) -> str:
    """Return the request's W3C or Cloud Run trace ID, or "" when neither header is well formed.

    Clients can set both headers, so accept only an exact, non-zero 32-digit lowercase hex ID.
    """
    for name, pattern in (("traceparent", _TRACEPARENT), ("x-cloud-trace-context", _CLOUD_TRACE_CONTEXT)):
        match = pattern.fullmatch(headers.get(name, ""))
        if match and match[1] != _NULL_TRACE_ID:
            return match[1]
    return ""


def trace_fields(cloud_trace: str = "") -> dict[str, str]:
    """Return log correlation fields: the Cloud Logging request trace and any active OpenTelemetry span."""
    fields = {CLOUD_TRACE_LOG_KEY: cloud_trace} if cloud_trace else {}
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        fields["trace_id"] = format(span_context.trace_id, "032x")
        fields["span_id"] = format(span_context.span_id, "016x")
    return fields


def _vary_accept_encoding(headers: MutableScopeHeaders) -> None:
    vary = headers.get("vary", "")
    if "accept-encoding" not in {item.strip().lower() for item in vary.split(",")}:
        headers.extend_header_value("vary", "Accept-Encoding")


# Google Analytics 4 after consent: gtag.js, its beacons and pixels (Google's CSP guide, without Google signals).
GA_SCRIPTS = "https://*.googletagmanager.com"
GA_IMAGES = "https://*.google-analytics.com https://*.googletagmanager.com"
GA_CONNECT = "https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com"


def _security_headers(nonce: str, environment: Environment) -> dict[str, str]:
    # 'strict-dynamic' trusts only nonce scripts and what they insert (gtag.js after consent),
    # so CSP3 browsers ignore the host allowlist that would let any Tag Manager container run;
    # 'self' and the host remain the fallback for browsers without 'strict-dynamic'.
    script_src = f"'self' 'nonce-{nonce}' 'strict-dynamic' {GA_SCRIPTS}"
    # Pages link one same-origin stylesheet; no inline <style> element is authorized.
    style_src = "'self'"
    headers = {
        "content-security-policy": "; ".join(
            (
                "default-src 'self'",
                "base-uri 'none'",
                "object-src 'none'",
                "frame-ancestors 'none'",
                "form-action 'self'",
                f"script-src {script_src}",
                f"style-src {style_src}",
                f"img-src 'self' data: {GA_IMAGES}",
                "font-src 'self'",
                f"connect-src 'self' {GA_CONNECT}",
            )
        )
        + ";",
        "referrer-policy": "strict-origin-when-cross-origin",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "cross-origin-opener-policy": "same-origin-allow-popups",
        "x-permitted-cross-domain-policies": "none",
        "x-xss-protection": "0",
        "permissions-policy": (
            "accelerometer=(), autoplay=(self), camera=(), display-capture=(), encrypted-media=(), fullscreen=(), "
            "geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), sync-xhr=(), usb=()"
        ),
    }
    if environment is Environment.PRODUCTION:
        headers["strict-transport-security"] = "max-age=63072000; includeSubDomains; preload"
    return headers


class SiteMiddleware:
    """Enforce the HTTP boundary and emit bounded structured request records."""

    def __init__(self, app: ASGIApp, config: Config, logger: Logger) -> None:
        self.app = app
        self.environment = config.environment
        self.project = config.google_cloud_project
        self.logger = logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        nonce = secrets.token_urlsafe(18)
        state["csp_nonce"] = nonce
        # Litestar routing rewrites scope["path"] (trailing slashes). Preserve the
        # public request path for observability and privacy decisions. This
        # boundary runs before Litestar routing, which collapses repeated
        # slashes: do the same so //mcp or //privacy cannot bypass path policy.
        path = _REPEATED_SLASHES.sub("/", scope.get("path", ""))
        state["request_path"] = path
        request_headers = Headers.from_scope(scope)
        # Correlate operational logs with the Cloud Run request log; analytics never carry it.
        trace_id = request_trace_id(request_headers) if self.project else ""
        cloud_trace = f"projects/{self.project}/traces/{trace_id}" if trace_id else ""
        state["cloud_trace"] = cloud_trace
        host = request_headers.get("host", "").partition(":")[0].lower()
        if self.environment is Environment.PRODUCTION and host == CANONICAL_APEX:
            await self._redirect(scope, send, nonce)
            return

        status = 200
        size_bytes = 0
        content_type = ""
        content_length = ""
        started_at = perf_counter()
        finalized = False

        def finalize_logs() -> None:
            nonlocal finalized
            if finalized:
                return
            finalized = True

            if not path.startswith("/static/") and path not in _SILENT_PATHS:
                log_values: dict[str, object] = {
                    "method": scope.get("method", ""),
                    "path": path,
                    "status": status,
                    "size_bytes": size_bytes,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                }
                log_values.update(trace_fields(cloud_trace))
                self.logger.info("http request processed", **log_values)

            # HEAD probes (link checkers, unfurlers) fetch no page, so they are not pageviews.
            if scope.get("method") == "GET" and content_type.startswith("text/html") and not 300 <= status < 400:
                query = parse_qs(scope.get("query_string", b"").decode("utf-8", "replace"), keep_blank_values=True)

                def first(name: str) -> str:
                    values = query.get(name)
                    return values[0] if values else ""

                self.logger.info(
                    ANALYTICS_LOG_NAME,
                    timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    path=analytics_path(path, status),
                    status=status,
                    referer=referer_host(request_headers.get("referer", "")),
                    utm_source=analytics_dimension(first("utm_source")),
                    utm_medium=analytics_dimension(first("utm_medium")),
                    utm_campaign=analytics_dimension(first("utm_campaign")),
                    # The public Cloud Run origin has no trusted geography
                    # header boundary. Preserve the sink schema without
                    # accepting a caller-controlled country dimension.
                    country="",
                    bot=is_bot(request_headers.get("user-agent", "")),
                )

        async def send_wrapper(message: Message) -> None:
            nonlocal content_length, content_type, size_bytes, status
            if message["type"] == "http.response.start":
                status = message["status"]
                response_headers = MutableScopeHeaders(message)
                for name, value in _security_headers(nonce, self.environment).items():
                    response_headers[name] = value
                _vary_accept_encoding(response_headers)
                if path in _MCP_PATHS:
                    # Protocol responses are per request. Prevent intermediaries
                    # from storing or transforming JSON-RPC envelopes.
                    response_headers["cache-control"] = "no-cache, no-transform"
                content_type = response_headers.get("content-type", "")
                content_length = response_headers.get("content-length", "")
            elif message["type"] == "http.response.body":
                size_bytes += len(message.get("body", b""))
            elif message["type"] == "http.response.pathsend":
                # The server sends the whole file; its declared length is the body size.
                size_bytes = int(content_length) if content_length.isdecimal() else 0
            await send(message)
            # Finalize while an inner OpenTelemetry request span is still
            # current, so ordinary logs retain trace correlation.
            if message["type"] == "http.response.pathsend" or (
                message["type"] == "http.response.body" and not message.get("more_body", False)
            ):
                finalize_logs()

        fetch_site = request_headers.get("sec-fetch-site", "")
        if (
            path in _MCP_PATHS
            and scope.get("method", "") not in _SAFE_METHODS
            and fetch_site not in _SAME_ORIGIN_FETCH_SITES
        ):
            # Fetch Metadata takes precedence
            # when a browser explicitly labels a non-safe request cross-origin.
            body = b"cross-origin request detected from Sec-Fetch-Site header\n"
            await send_wrapper(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"text/plain; charset=utf-8"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send_wrapper({"type": "http.response.body", "body": body, "more_body": False})
            return

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException:
            # The server owns exception rendering, but an escaping failure must
            # still be represented honestly in the request log.
            status = 500
            raise
        finally:
            # Also covers a non-conforming ASGI app that returns without a
            # terminal body event. Normal responses already finalized while
            # the inner OpenTelemetry span was current.
            finalize_logs()

    async def _redirect(self, scope: Scope, send: Send, nonce: str) -> None:
        raw_path = scope.get("raw_path", scope.get("path", "").encode()).split(b"?", 1)[0]
        path = raw_path.decode("latin-1")
        query = scope.get("query_string", b"")
        location = CANONICAL_TARGET + path
        if query:
            location += "?" + query.decode("latin-1")
        headers = [(b"location", location.encode("latin-1")), (b"content-length", b"0")]
        # 308 keeps the method and body, so an apex POST /mcp is not replayed as a GET.
        status = 301 if scope.get("method", "GET") in {"GET", "HEAD"} else 308
        start: Message = {"type": "http.response.start", "status": status, "headers": headers}
        mutable = MutableScopeHeaders(start)
        for name, value in _security_headers(nonce, self.environment).items():
            mutable[name] = value
        _vary_accept_encoding(mutable)
        await send(start)
        await send({"type": "http.response.body", "body": b"", "more_body": False})
