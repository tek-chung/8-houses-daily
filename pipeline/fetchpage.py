"""Fetching. Spec §11.1, substantially revised after Phase 0 reconnaissance.

The original version hashed the whole page and sent the whole page to the model.
Reconnaissance against real charity sites showed why that fails:

  Glass Door's volunteer page returned roughly 6,000 tokens of navigation, tag
  clouds, "Latest" and "Most read" blocks around about 200 tokens of role content.

Two failures follow. The model sees "Sleep Out", "London Marathon" and "Challenge
Events" in the navigation and can invent roles from them. And — worse — the sidebar
rotates whenever the charity publishes news, so the content hash changes every week
on every page. All 34 look changed every run, everything gets re-extracted, and the
review queue is permanently full. The maintainer stops reading it within a month and
the whole freshness premise dies quietly.

So this module now does three things it didn't:

  1. Isolates the main content region before hashing or extracting.
  2. Hashes only that region, so the hash tracks role content and nothing else.
  3. Follows role links one level down, because most charity CMSes put the landing
     page's real content on sub-pages.

It also captures a CMS-published "last updated" date where one exists — a better
freshness signal than anything we can infer.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from config import (HTTP_CACHE, MAX_PAGE_CHARS, MAX_ROLE_SUBPAGES,
                    MIN_MAIN_CONTENT_CHARS, REQUEST_DELAY_SECONDS,
                    REQUEST_TIMEOUT_SECONDS, USER_AGENT)

_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
_last_request_at = 0.0

_STRIP_TAGS = ["nav", "header", "footer", "aside", "form", "script", "style",
               "noscript", "svg", "iframe"]
_STRIP_PATTERNS = re.compile(
    r"(nav|menu|breadcrumb|sidebar|side-bar|footer|header|cookie|banner|social|"
    r"share|tag-cloud|tagcloud|most-read|mostread|latest|related|newsletter|"
    r"signup|sign-up|search|skip|basket|cart|translate|gtranslate)", re.I)

# Link text suggesting a page that describes a role.
_ROLE_LINK_HINTS = re.compile(
    r"(volunteer|volunteering|befriend|mentor|mentoring|host|hosting|trustee|"
    r"night shelter|shelter volunteer|peer|lived experience|shop|drop-in|"
    r"outreach|kitchen|role|opportunit)", re.I)
# ...but these are not roles, however volunteer-ish they sound.
_ROLE_LINK_BLOCK = re.compile(
    r"(donate|donation|fundrais|marathon|sleep ?out|challenge event|cycle|"
    r"half.?marathon|10k|legacy|gift.?aid|shop online|job|vacanc|career|"
    r"privacy|cookie|terms|complaint|sitemap|login|basket|/news|blog)", re.I)

_UPDATED_RE = re.compile(
    r"(?:last\s+)?updated[:\s]*"
    r"(\d{1,2}(?:st|nd|rd|th)?\s+\w+,?\s+\d{4}|\d{4}-\d{2}-\d{2})", re.I)


@dataclass
class FetchResult:
    status: str            # changed | unchanged | blocked | failed
    text: str | None = None
    content_hash: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    final_url: str | None = None
    redirected: bool = False
    error: str | None = None
    pages_read: list[str] = field(default_factory=list)
    cms_updated: str | None = None
    boilerplate_ratio: float | None = None


def _throttle() -> None:
    global _last_request_at
    wait = REQUEST_DELAY_SECONDS - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def robots_allows(url: str) -> bool:
    origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if origin not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(urljoin(origin, "/robots.txt"))
        try:
            _throttle()
            with httpx.Client(headers={"User-Agent": USER_AGENT},
                              timeout=REQUEST_TIMEOUT_SECONDS,
                              follow_redirects=True) as c:
                r = c.get(urljoin(origin, "/robots.txt"))
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _robots_cache[origin] = rp
    return _robots_cache[origin].can_fetch(USER_AGENT, url)


# ------------------------------------------------------------- content isolation

def main_content(html: str) -> str:
    """Return the page's main content with boilerplate removed.

    trafilatura first — purpose-built for this and handles most CMS layouts. A
    conservative DOM-stripping fallback catches what it gives up on, because
    returning nothing would look identical to a client-rendered page and we would
    misdiagnose the site.
    """
    try:
        got = trafilatura.extract(
            html, include_comments=False, include_tables=True,
            include_links=False, favor_precision=True)
        if got and len(got) >= MIN_MAIN_CONTENT_CHARS:
            return got.strip()[:MAX_PAGE_CHARS]
    except Exception:
        pass

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    for attr in ("class", "id"):
        for el in soup.find_all(attrs={attr: _STRIP_PATTERNS}):
            el.decompose()

    node = (soup.find("main") or soup.find(attrs={"role": "main"})
            or soup.find("article") or soup.body or soup)
    text = node.get_text("\n")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()[:MAX_PAGE_CHARS]


def full_text(html: str) -> str:
    """Whole-page text, used only to measure how much was boilerplate."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


# Framework mount points and hydration markers. Their presence alongside almost no
# text means the content is rendered client-side.
_SPA_MARKERS = re.compile(
    r'(id=["\'](?:root|app|__next|__nuxt|q-app)["\']|data-reactroot|data-react-helmet|'
    r'data-server-rendered|ng-app|ng-version|__NEXT_DATA__|__NUXT__|'
    r'window\.__INITIAL_STATE__|v-cloak)', re.I)


def looks_client_rendered(html: str) -> bool:
    """Distinguish 'no text because JavaScript' from 'no text because thin'.

    This distinction decides what the maintainer does next, so getting it wrong is
    expensive. A client-rendered page needs a headless browser or a different URL.
    A genuinely thin page — a real 'please get in touch' page with two sentences on
    it — will never yield role detail no matter what we throw at it, and should be
    treated as link-only permanently.

    Signals for client-rendered: a framework mount point, or heavy script use with
    essentially no prose in paragraph elements.
    """
    if _SPA_MARKERS.search(html):
        return True
    soup = BeautifulSoup(html, "html.parser")
    scripts = len(soup.find_all("script"))
    prose = sum(len(p.get_text(" ").strip())
                for p in soup.find_all(["p", "li", "dd", "blockquote"]))
    return prose < 80 and scripts >= 1


def cms_updated(html: str) -> str | None:
    """Some CMSes publish their own last-updated date. Better than our hash."""
    m = _UPDATED_RE.search(full_text(html)[:20_000])
    return m.group(1).strip() if m else None


def find_role_links(html: str, base_url: str) -> list[str]:
    """Links from a volunteering landing page that look like role detail pages."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "aside"]):
        tag.decompose()

    origin = urlparse(base_url).netloc
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ").strip()
        href = urldefrag(urljoin(base_url, a["href"]))[0]
        if not label or len(label) > 90:
            continue
        if urlparse(href).netloc != origin:
            continue
        if href.rstrip("/") == base_url.rstrip("/") or href in seen:
            continue
        haystack = f"{label} {href}"
        if _ROLE_LINK_BLOCK.search(haystack):
            continue
        if not _ROLE_LINK_HINTS.search(haystack):
            continue
        seen.add(href)
        out.append(href)
    return out[:MAX_ROLE_SUBPAGES]


# ------------------------------------------------------------- http

def _load_cache() -> dict:
    return json.loads(HTTP_CACHE.read_text(encoding="utf-8")) if HTTP_CACHE.exists() else {}


def _save_cache(cache: dict) -> None:
    HTTP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    HTTP_CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def _get(url: str, headers: dict) -> httpx.Response:
    _throttle()
    with httpx.Client(follow_redirects=True,
                      timeout=REQUEST_TIMEOUT_SECONDS) as client:
        return client.get(url, headers=headers)


def fetch(url: str, known_hash: str | None = None,
          follow_roles: bool = True) -> FetchResult:
    """Fetch a volunteering page plus its role sub-pages as one payload."""
    if not robots_allows(url):
        return FetchResult("blocked", error="disallowed by robots.txt")

    cache = _load_cache()
    entry = cache.get(url, {})
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    if entry.get("etag"):
        headers["If-None-Match"] = entry["etag"]
    if entry.get("last_modified"):
        headers["If-Modified-Since"] = entry["last_modified"]

    try:
        r = _get(url, headers)
    except Exception as exc:
        return FetchResult("failed", error=f"{type(exc).__name__}: {exc}")

    if r.status_code == 304:
        return FetchResult("unchanged", content_hash=known_hash,
                           etag=entry.get("etag"),
                           last_modified=entry.get("last_modified"),
                           final_url=url, pages_read=[url])
    if r.status_code >= 400:
        return FetchResult("failed", error=f"HTTP {r.status_code}")

    html = r.text
    main = main_content(html)
    whole = full_text(html)
    ratio = 1 - (len(main) / len(whole)) if whole else None

    if len(main) < MIN_MAIN_CONTENT_CHARS:
        why = ("content is rendered in-browser" if looks_client_rendered(html)
               else "the page genuinely has almost no text on it")
        return FetchResult("failed", boilerplate_ratio=ratio,
                           error=f"only {len(main)} chars extractable — {why}")

    sections, pages = [f"## Page: {url}\n\n{main}"], [url]

    if follow_roles:
        for link in find_role_links(html, url):
            if not robots_allows(link):
                continue
            try:
                rr = _get(link, {"User-Agent": USER_AGENT})
                if rr.status_code >= 400:
                    continue
                sub = main_content(rr.text)
            except Exception:
                continue
            if len(sub) >= MIN_MAIN_CONTENT_CHARS:
                sections.append(f"## Page: {link}\n\n{sub}")
                pages.append(link)

    combined = "\n\n".join(sections)[:MAX_PAGE_CHARS]

    # The fix: hash main content only, order-independent, so the hash tracks role
    # content and ignores the news sidebar that rotates every week.
    digest = hashlib.sha256("\n\n".join(sorted(sections)).encode()).hexdigest()

    etag, last_mod = r.headers.get("ETag"), r.headers.get("Last-Modified")
    cache[url] = {"etag": etag, "last_modified": last_mod, "hash": digest}
    _save_cache(cache)

    final = str(r.url)
    return FetchResult(
        "unchanged" if digest == known_hash else "changed",
        text=combined, content_hash=digest, etag=etag, last_modified=last_mod,
        final_url=final, redirected=final.rstrip("/") != url.rstrip("/"),
        pages_read=pages, cms_updated=cms_updated(html),
        boilerplate_ratio=round(ratio, 3) if ratio is not None else None,
    )
