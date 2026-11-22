"""SSRF-hardened HTTPS fetcher and source extractors for daily news curation."""

import base64
import html
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
import urllib.request
import zlib
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import IO, Any
from urllib.parse import quote, urlparse
from xml.etree import ElementTree

from www.news import canonicalize_url, load_news

EXCERPT_LIMIT = 1500
MAX_BYTES = 1_200_000
TIMEOUT_SECONDS = 8.0  # per socket operation
DEADLINE_SECONDS = 20.0  # per source read, redirects included
WORKERS = 8
SHORTENERS = frozenset({"t.co", "bit.ly", "tinyurl.com", "lnkd.in", "buff.ly"})
USER_AGENT = "Mozilla/5.0 (compatible; fmind-news; +https://www.fmind.dev/news/)"
ACCEPT_HEADER = "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7"
AISTUDIO_MANIFEST = "https://www.gstatic.com/aistudio-static/editorial/pages/_manifest.json"
AISTUDIO_PAGES = "https://www.gstatic.com/aistudio-static/editorial/pages"
_GZIP_MAGIC = b"\x1f\x8b"

type Fetch = Callable[[str], tuple[str, str]]


def normalized_host(url: str) -> str:
    """Return a lowercase hostname without trailing FQDN dot or port."""
    return (urlparse(url).hostname or "").rstrip(".").lower()


class HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse a redirect off HTTPS before urllib sends the next request (its default follows http and ftp)."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        if urlparse(newurl).scheme != "https":
            fp.close()
            raise ValueError(f"{req.full_url} redirected to non-HTTPS {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


_TLS_CONTEXT = _tls_context()
# RFC 6052 Well-Known Prefix embeds arbitrary IPv4 addresses (including loopback and
# cloud metadata) inside IPv6; Python's ipaddress marks 64:ff9b::/96 as global.
_RFC6052_NAT64 = ipaddress.IPv6Network("64:ff9b::/96")


class PublicHTTPSConnection(http.client.HTTPSConnection):
    """Connect only to globally routable IPs, binding socket and TLS SNI without re-resolving DNS."""

    def connect(self) -> None:
        infos = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        if not infos:
            raise OSError(f"{self.host}: no address found")
        for _, _, _, _, sockaddr in infos:
            address = ipaddress.ip_address(sockaddr[0])
            if not address.is_global or (isinstance(address, ipaddress.IPv6Address) and address in _RFC6052_NAT64):
                raise ValueError(f"refusing non-global address {address} for {self.host}")
        last_error: OSError | None = None
        for family, socktype, proto, _, sockaddr in infos:
            raw: socket.socket | None = None
            try:
                raw = socket.socket(family, socktype, proto)
                if isinstance(self.timeout, int | float):
                    raw.settimeout(self.timeout)
                raw.connect(sockaddr)
                self.sock = _TLS_CONTEXT.wrap_socket(raw, server_hostname=self.host)
                return
            except OSError as error:
                if raw is not None:
                    raw.close()
                last_error = error
        if last_error is not None:
            raise last_error


class PublicHTTPSHandler(urllib.request.HTTPSHandler):
    """Route HTTPS fetches through PublicHTTPSConnection."""

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(PublicHTTPSConnection, req, context=_TLS_CONTEXT)


OPENER = urllib.request.build_opener(HttpsOnlyRedirect, PublicHTTPSHandler)


def _decompress(url: str, body: bytes, encoding: str, max_bytes: int) -> bytes:
    """Decompress gzip or deflate HTTP payloads (including truncated streams) within `max_bytes`."""
    kind = encoding.lower().strip()
    if kind in ("gzip", "x-gzip") or body.startswith(_GZIP_MAGIC):
        decompressor = zlib.decompressobj(zlib.MAX_WBITS | 16)
    elif kind == "deflate":
        decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
    else:
        return body
    try:
        return decompressor.decompress(body, max_bytes)
    except zlib.error as error:
        if kind == "deflate":
            try:
                return zlib.decompressobj().decompress(body, max_bytes)
            except zlib.error:
                pass
        raise OSError(f"{url}: {type(error).__name__}: {error}") from error


def fetch_text(url: str, max_bytes: int = MAX_BYTES) -> tuple[str, str]:
    """Return the final URL and decoded body of one bounded, deadline-limited HTTPS read."""
    if urlparse(url).scheme != "https":
        raise ValueError(f"refusing non-HTTPS URL {url!r}")
    deadline = time.monotonic() + DEADLINE_SECONDS
    headers = {"User-Agent": USER_AGENT, "Accept": ACCEPT_HEADER, "Accept-Encoding": "gzip, deflate"}
    request = urllib.request.Request(url, headers=headers)  # noqa: S310
    body = bytearray()
    try:
        with OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
            # read1 returns as soon as any bytes arrive, so a trickling server meets the deadline check.
            while len(body) < max_bytes and (chunk := response.read1(max_bytes - len(body))):
                body += chunk
                if time.monotonic() > deadline:
                    raise TimeoutError(f"{url}: read exceeded {DEADLINE_SECONDS:g} s")
            final_url = response.geturl() or url
            encoding = getattr(response, "headers", {}).get("Content-Encoding", "")
    except http.client.HTTPException as error:
        # IncompleteRead, BadStatusLine, and LineTooLong are not OSErrors, and urllib does not wrap them.
        raise OSError(f"{url}: {type(error).__name__}: {error}") from error
    decoded = _decompress(url, bytes(body), encoding, max_bytes).decode("utf-8", errors="replace")
    return final_url, decoded


def _json_object(body: str) -> dict[str, Any]:
    """Parse an API body that must be a JSON object, so a list or null fails as a fetch error."""
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object, got {type(data).__name__}")
    return data


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _first(patterns: Sequence[str], text: str) -> str:
    for pattern in patterns:
        if match := re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            value = _clean(next((group for group in match.groups() if group), ""))
            if value:
                return value
    return ""


def _meta(name: str) -> tuple[str, str]:
    attribute = "property" if name.startswith("og:") else "name"
    escaped = re.escape(name)
    return (
        rf"<meta\b[^>]{'{0,2048}'}?{attribute}=[\"']{escaped}[\"'][^>]{'{0,2048}'}?content=(?:\"([^\"]+)\"|'([^']+)')",
        rf"<meta\b[^>]{'{0,2048}'}?content=(?:\"([^\"]+)\"|'([^']+)')[^>]{'{0,2048}'}?{attribute}=[\"']{escaped}[\"']",
    )


def _minutes(seconds: int) -> str:
    minutes = max(1, round(seconds / 60))
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{minutes}m"
    return f"{hours}h {rest}m" if rest else f"{hours}h"


def _youtube(url: str, fetch: Fetch) -> dict[str, str]:
    _, oembed = fetch(f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json")
    data = _json_object(oembed)
    facts = {"title": _clean(data.get("title", ""))}
    try:
        _, page = fetch(url)
        if seconds := re.search(r'"lengthSeconds":"(\d+)"', page):
            facts["duration"] = _minutes(int(seconds[1]))
        if short := re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', page):
            text = _clean(json.loads(f'"{short[1]}"'))
            facts["description"] = text[:600]
            facts["excerpt"] = text[:EXCERPT_LIMIT]
    except (OSError, ValueError) as error:
        facts["error"] = f"watch page: {type(error).__name__}: {error}"
    return facts


def _x(url: str, fetch: Fetch) -> dict[str, str]:
    _, oembed = fetch(f"https://publish.twitter.com/oembed?url={quote(url, safe='')}")
    data = _json_object(oembed)
    author = _clean(data.get("author_name", ""))
    text = _clean(re.sub(r"<[^>]+>", " ", data.get("html", "")))
    return {"title": f"{author} on X" if author else "X post", "description": text[:600], "excerpt": text}


def _github(url: str, fetch: Fetch) -> dict[str, str]:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) != 2:
        return _page(url, fetch)
    owner, repo = parts[0], parts[1]
    try:
        _, body = fetch(f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}")
    except OSError:
        # Also the answer for site pages shaped like a repository, such as /blog/x or /topics/x: the API has no such repo.
        return _page(url, fetch)
    data = _json_object(body)
    description = _clean(data.get("description") or "")
    result = {"title": _clean(data.get("full_name") or "") or f"{owner}/{repo}", "description": description}
    try:
        # The API finds the README whatever its name or format (README.md, readme.rst, docs/README.md).
        _, body = fetch(f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}/readme")
        readme = base64.b64decode(json.loads(body)["content"]).decode("utf-8", errors="replace")
    except (OSError, ValueError, KeyError, TypeError) as error:
        result["error"] = f"README: {type(error).__name__}: {error}"
        readme = ""
    readme = re.sub(r"```.*?```", " ", readme, flags=re.DOTALL)
    readme = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", readme)
    readme = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", readme)
    readme_text = _clean(re.sub(r"<[^>]+>", " ", readme))
    if not description and not readme_text:
        return result
    facts = [
        f"License: {spdx}."
        for spdx in [(data.get("license") or {}).get("spdx_id")]
        if spdx not in (None, "NOASSERTION")
    ]
    if topics := data.get("topics"):
        facts.append(f"Topics: {', '.join(topics[:8])}.")
    if readme_text:
        facts.append(readme_text)
    return result | {"excerpt": _clean(" ".join(facts))}


def _arxiv(url: str, fetch: Fetch) -> dict[str, str]:
    paper = urlparse(url).path.split("/abs/")[-1].strip("/")
    _, body = fetch(f"https://export.arxiv.org/api/query?id_list={quote(paper)}")
    folded = body.lower()
    if "<!doctype" in folded or "<!entity" in folded:
        raise ValueError("arXiv response contains disallowed XML declarations")
    namespace = {"a": "http://www.w3.org/2005/Atom"}
    entry = ElementTree.fromstring(body).find("a:entry", namespace)  # noqa: S314 - DTD/ENTITY rejected above
    if entry is None:
        return {}
    summary = _clean(entry.findtext("a:summary", default="", namespaces=namespace))
    return {
        "title": _clean(entry.findtext("a:title", default="", namespaces=namespace)),
        "description": summary[:600],
        "excerpt": summary,
    }


# The lookahead ends the tag name, so custom elements such as <nav-menu> or <main-content> do not match.
_BOILERPLATE = re.compile(r"<(script|style|noscript|nav|header|footer|aside|svg|form)(?=[\s/>])[^>]*>", re.IGNORECASE)
_SCOPE = re.compile(r"<(article|main)(?=[\s/>])[^>]*>", re.IGNORECASE)


def _blocks(text: str, opener: re.Pattern[str]) -> Iterator[tuple[re.Match[str], re.Match[str]]]:
    """Yield non-overlapping (opener, first closer) pairs, as `<(tag)...>.*?</\\1>` would, in linear time.

    That regex rescans to the end for every unclosed opener, which is quadratic. Here an opener without a closer
    marks its tag as unclosed, so each tag's closer searches cover disjoint spans of the page.
    """
    position, unclosed = 0, set[str]()
    for start in opener.finditer(text):
        tag = start[1].lower()
        if start.start() < position or tag in unclosed:
            continue
        if (end := re.compile(rf"</{tag}\s*>", re.IGNORECASE).search(text, start.end())) is None:
            unclosed.add(tag)
            continue
        position = end.end()
        yield start, end


def _page(url: str, fetch: Fetch) -> dict[str, str]:
    final_url, page = fetch(url)
    title = _first((*_meta("og:title"), r"<title[^>]*>(.*?)</title>"), page)
    description = _first((*_meta("og:description"), *_meta("description")), page)
    parts, position = [], 0
    for start, end in _blocks(page, _BOILERPLATE):
        parts += (page[position : start.start()], " ")
        position = end.end()
    body = "".join((*parts, page[position:]))
    scope = next((body[start.end() : end.start()] for start, end in _blocks(body, _SCOPE)), body)
    paragraphs = " ".join(re.findall(r"<p\b[^>]*>(.*?)</p>", scope, re.IGNORECASE | re.DOTALL))
    text = _clean(re.sub(r"<[^>]+>", " ", paragraphs or scope))
    words = len(text.split())
    facts = {"title": title, "description": description, "excerpt": text}
    if final_url and final_url != url:
        facts["final_url"] = final_url
    if words >= 80:
        facts["duration"] = f"{max(1, round(words / 220))}m read"
    return facts


_EDITORIAL_KEYS = frozenset({"headline", "subhead", "body", "text", "description"})


def _collect_editorial_text(node: object, pieces: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _EDITORIAL_KEYS and isinstance(value, str):
                cleaned = _clean(re.sub(r"<[^>]+>", " ", value))
                if cleaned:
                    pieces.append(cleaned)
            else:
                _collect_editorial_text(value, pieces)
    elif isinstance(node, list):
        for item in node:
            _collect_editorial_text(item, pieces)


def _aistudio(url: str, fetch: Fetch) -> dict[str, str]:
    path = urlparse(url).path.strip("/")
    if path.startswith("docs"):
        stem = path.removesuffix(".md")
        _, text = fetch(f"https://aistudio.google.com/{stem}.md")
        match = re.search(r"^#[ \t]+([^\n]+?)(?:[ \t]+\{%[^\n]*)?$", text, re.MULTILINE)
        title = _clean(match[1]) if match else ""
        body = _clean(re.sub(r"<[^>]+>|\{%.*?%\}", " ", text))
        return {"title": title, "description": body[:600], "excerpt": body}
    if not path.startswith("learn/"):
        return _page(url, fetch)
    slug = path.removeprefix("learn/").strip("/")
    _, raw_manifest = fetch(AISTUDIO_MANIFEST)
    pages = _json_object(raw_manifest).get("pages")
    if not isinstance(pages, dict) or not isinstance(meta := pages.get(slug), dict):
        return {}
    facts = {"title": _clean(meta.get("title") or ""), "description": _clean(meta.get("description") or "")}
    if content_id := meta.get("contentId"):
        try:
            _, raw_page = fetch(f"{AISTUDIO_PAGES}/{quote(str(content_id))}.json")
            editorial_page = _json_object(raw_page)
            pieces: list[str] = []
            _collect_editorial_text(editorial_page, pieces)
            facts["excerpt"] = _clean(" ".join(pieces))
        except (OSError, ValueError) as error:
            facts["error"] = f"editorial page: {type(error).__name__}: {error}"
    return facts


def source_facts(url: str, fetch: Fetch = fetch_text) -> dict[str, str]:
    """Collect the title, description, text excerpt, and duration that ground an edition line."""
    host = normalized_host(url)
    reader = _page
    if host == "www.youtube.com":
        reader = _youtube
    elif host == "x.com":
        reader = _x
    elif host == "github.com":
        reader = _github
    elif host == "arxiv.org" and "/abs/" in url:
        reader = _arxiv
    elif host == "aistudio.google.com":
        reader = _aistudio
    result = {"url": url, "title": "", "description": "", "excerpt": "", "duration": ""}
    try:
        result.update(reader(url, fetch))
    except (OSError, ValueError, ElementTree.ParseError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    except (TypeError, AttributeError, KeyError) as error:
        # An API field of another type, such as a numeric description, fails this link only, not the batch.
        result["error"] = f"{type(error).__name__}: {url} returned a field of an unexpected type: {error}"
    result["excerpt"] = result["excerpt"][:EXCERPT_LIMIT]
    has_facts = bool(result["title"] and (result["description"] or result["excerpt"]))
    return {"status": "ok" if has_facts else "fetch_error", **result}


def prepare(
    urls: Sequence[str], news_dir: Path = Path("content/news"), fetch: Fetch = fetch_text
) -> list[dict[str, str]]:
    """Canonicalize each URL, skip those in any edition (today's included) or repeated, and fetch facts for the rest."""
    published = {canonicalize_url(item.url): edition.slug for edition in load_news(news_dir) for item in edition.items}
    results: list[dict[str, str]] = []
    pending: list[str] = []
    for raw in urls:
        try:
            url = canonicalize_url(raw)
            if normalized_host(url) in SHORTENERS:
                url = canonicalize_url(fetch(url)[0])
        except (OSError, ValueError) as error:
            results.append({"status": "invalid", "url": raw, "error": f"{type(error).__name__}: {error}"})
            continue
        if url in published:
            results.append({"status": "duplicate", "url": url, "edition": published[url]})
        elif url in pending:
            results.append({"status": "duplicate", "url": url, "edition": "this batch"})
        else:
            pending.append(url)
    if pending:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(pending))) as pool:
            results.extend(pool.map(lambda url: source_facts(url, fetch), pending))
    return results
