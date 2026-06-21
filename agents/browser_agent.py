"""browser_agent.py — DuckDuckGo search and webpage retrieval plugin (TOOL ONLY).

This module is a *pure tool*. It performs **no** analysis, summarization,
reasoning, classification, decision making, intent detection, opinion
generation, or content interpretation. It only:

    1. Receives a JSON-compatible ``dict`` request.
    2. Searches DuckDuckGo or fetches/crawls webpages.
    3. Extracts raw content and metadata.
    4. Returns a JSON-compatible ``dict`` response.

All intelligence belongs to the calling "Brain Agent". The single public
entry point is :func:`execute`.

Dependencies (install once)::

    pip install ddgs requests beautifulsoup4 lxml

No API keys required.

CLI usage::

    python browser_agent.py request.json
    python browser_agent.py '{"action": "web_search", "parameters": {"query": "AI news"}}'
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Callable, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS  # noqa: F811

__all__ = ["execute", "PLUGIN_INFO"]


# --------------------------------------------------------------------------- #
# Plugin metadata
# --------------------------------------------------------------------------- #
PLUGIN_INFO: dict[str, str] = {
    "name": "browser_agent",
    "agent_name": "BrowserAgent",
    "version": "1.0.0",
    "type": "tool",
    "input_format": "json",
    "output_format": "json",
    "entrypoint": "execute",
    "description": "DuckDuckGo search and webpage retrieval plugin",
}


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
REQUEST_TIMEOUT: int = 20
MAX_RETRIES: int = 3
RETRY_BACKOFF: float = 1.0
DEFAULT_MAX_RESULTS: int = 10
MAX_RESULTS_CAP: int = 50
DEFAULT_MAX_PAGES: int = 10
MAX_PAGES_CAP: int = 50
MAX_HTML_SIZE: int = 10 * 1024 * 1024  # 10 MB

USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class BrowserAgentError(Exception):
    """Raised for any handled error whose message is safe to return."""


# --------------------------------------------------------------------------- #
# HTTP layer (with retry/backoff)
# --------------------------------------------------------------------------- #
_SESSION: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Return a cached :class:`requests.Session` with a realistic UA."""
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({"User-Agent": USER_AGENT})
    return _SESSION


def _fetch_url(url: str, *, timeout: int = REQUEST_TIMEOUT) -> requests.Response:
    """GET *url* with retry/backoff.

    Retries on network errors and HTTP 5xx. Client errors (4xx) are
    surfaced immediately.
    """
    session = _get_session()
    last_error: str = "unknown error"

    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
        except requests.RequestException as exc:
            last_error = f"network error ({exc})"
        else:
            if resp.status_code >= 500:
                last_error = f"server error (HTTP {resp.status_code})"
            elif resp.status_code >= 400:
                raise BrowserAgentError(
                    f"HTTP {resp.status_code} for {url}"
                )
            else:
                content_length = len(resp.content)
                if content_length > MAX_HTML_SIZE:
                    raise BrowserAgentError(
                        f"Page too large ({content_length:,} bytes, limit {MAX_HTML_SIZE:,})"
                    )
                return resp

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF * (2 ** attempt))

    raise BrowserAgentError(f"Failed after {MAX_RETRIES} attempts: {last_error}")


# --------------------------------------------------------------------------- #
# HTML parsing helpers
# --------------------------------------------------------------------------- #
def _make_soup(html: str) -> BeautifulSoup:
    """Parse HTML with lxml (fast) falling back to html.parser."""
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _extract_title(soup: BeautifulSoup) -> str:
    """Return the page <title> text or empty string."""
    tag = soup.find("title")
    return tag.get_text(strip=True) if tag else ""


def _extract_text(soup: BeautifulSoup) -> str:
    """Return visible text from the page, stripping scripts/styles."""
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
    """Return all <a> links with resolved absolute URLs."""
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if href in seen:
            continue
        seen.add(href)
        text = a.get_text(strip=True)
        links.append({"url": href, "text": text})
    return links


def _extract_images(soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
    """Return all <img> sources with resolved absolute URLs."""
    images: list[dict[str, str]] = []
    seen: set[str] = set()
    for img in soup.find_all("img", src=True):
        src = urljoin(base_url, img["src"])
        if src in seen:
            continue
        seen.add(src)
        alt = img.get("alt", "")
        images.append({"url": src, "alt": alt})
    return images


def _extract_metadata(soup: BeautifulSoup, url: str) -> dict[str, Any]:
    """Return standard page metadata from <meta> tags."""
    title = _extract_title(soup)

    description = ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag and desc_tag.get("content"):
        description = desc_tag["content"]
    if not description:
        og_desc = soup.find("meta", attrs={"property": "og:description"})
        if og_desc and og_desc.get("content"):
            description = og_desc["content"]

    keywords: list[str] = []
    kw_tag = soup.find("meta", attrs={"name": "keywords"})
    if kw_tag and kw_tag.get("content"):
        keywords = [k.strip() for k in kw_tag["content"].split(",") if k.strip()]

    canonical = ""
    canon_tag = soup.find("link", attrs={"rel": "canonical"})
    if canon_tag and canon_tag.get("href"):
        canonical = canon_tag["href"]

    return {
        "title": title,
        "description": description,
        "keywords": keywords,
        "canonical_url": canonical or url,
    }


def _fetch_and_parse(url: str) -> dict[str, Any]:
    """Fetch a URL and return a full page dict (url, title, text, html, links, images)."""
    resp = _fetch_url(url)
    html = resp.text
    soup = _make_soup(html)
    return {
        "url": resp.url,
        "title": _extract_title(soup),
        "text": _extract_text(soup),
        "html": html,
        "links": _extract_links(soup, resp.url),
        "images": _extract_images(soup, resp.url),
    }


# --------------------------------------------------------------------------- #
# DuckDuckGo search helper
# --------------------------------------------------------------------------- #
def _ddg_search(query: str, max_results: int) -> list[dict[str, str]]:
    """Run a DuckDuckGo text search and normalise the result keys."""
    try:
        ddgs = DDGS()
        raw = ddgs.text(query, max_results=max_results, backend="html")
        if not raw:
            raw = ddgs.text(query, max_results=max_results, backend="lite")
    except Exception as exc:
        raise BrowserAgentError(f"DuckDuckGo search failed: {exc}")

    results: list[dict[str, str]] = []
    for item in raw:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("href", ""),
            "snippet": item.get("body", ""),
        })
    return results


def _clamp_max_results(params: dict[str, Any], key: str = "max_results") -> int:
    """Parse and clamp a max_results parameter."""
    raw = params.get(key, DEFAULT_MAX_RESULTS)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise BrowserAgentError(f"Parameter '{key}' must be an integer")
    if n < 1:
        n = 1
    if n > MAX_RESULTS_CAP:
        n = MAX_RESULTS_CAP
    return n


# --------------------------------------------------------------------------- #
# Action handlers
# --------------------------------------------------------------------------- #
def _action_web_search(params: dict[str, Any]) -> dict[str, Any]:
    query = params.get("query", "")
    max_results = _clamp_max_results(params)
    results = _ddg_search(query, max_results)
    return {"count": len(results), "results": results}


def _action_multi_search(params: dict[str, Any]) -> dict[str, Any]:
    queries = params.get("queries")
    if not queries or not isinstance(queries, list):
        raise BrowserAgentError("Missing or invalid queries parameter (expected a list)")
    if not all(isinstance(q, str) and q.strip() for q in queries):
        raise BrowserAgentError("All queries must be non-empty strings")
    max_results = _clamp_max_results(params)

    results: dict[str, Any] = {}
    for query in queries:
        try:
            results[query] = _ddg_search(query.strip(), max_results)
        except BrowserAgentError as exc:
            results[query] = {"error": str(exc)}
    return {"results": results}


def _action_fetch_page(params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url", "")
    return _fetch_and_parse(url)


def _action_fetch_multiple_pages(params: dict[str, Any]) -> dict[str, Any]:
    urls = params.get("urls")
    if not urls or not isinstance(urls, list):
        raise BrowserAgentError("Missing or invalid urls parameter (expected a list)")
    if not all(isinstance(u, str) and u.strip() for u in urls):
        raise BrowserAgentError("All urls must be non-empty strings")

    results: list[dict[str, Any]] = []
    for url in urls:
        try:
            page = _fetch_and_parse(url.strip())
            results.append({"status": "success", "url": url, "data": page})
        except (BrowserAgentError, Exception) as exc:
            results.append({"status": "error", "url": url, "message": str(exc)})
    return {"count": len(results), "results": results}


def _action_extract_text(params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url", "")
    resp = _fetch_url(url)
    soup = _make_soup(resp.text)
    return {"url": resp.url, "text": _extract_text(soup)}


def _action_extract_links(params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url", "")
    resp = _fetch_url(url)
    soup = _make_soup(resp.text)
    links = _extract_links(soup, resp.url)
    return {"url": resp.url, "count": len(links), "links": links}


def _action_extract_images(params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url", "")
    resp = _fetch_url(url)
    soup = _make_soup(resp.text)
    images = _extract_images(soup, resp.url)
    return {"url": resp.url, "count": len(images), "images": images}


def _action_get_page_metadata(params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url", "")
    resp = _fetch_url(url)
    soup = _make_soup(resp.text)
    return _extract_metadata(soup, resp.url)


def _action_crawl_website(params: dict[str, Any]) -> dict[str, Any]:
    start_url = params.get("url", "")
    max_pages_raw = params.get("max_pages", DEFAULT_MAX_PAGES)
    try:
        max_pages = int(max_pages_raw)
    except (TypeError, ValueError):
        raise BrowserAgentError("max_pages must be an integer")
    if max_pages < 1:
        max_pages = 1
    if max_pages > MAX_PAGES_CAP:
        max_pages = MAX_PAGES_CAP

    parsed_start = urlparse(start_url)
    domain = parsed_start.netloc

    visited: set[str] = set()
    queue: list[str] = [start_url]
    pages: list[dict[str, Any]] = []

    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        normalised = urlparse(url)._replace(fragment="").geturl()
        if normalised in visited:
            continue
        visited.add(normalised)

        try:
            resp = _fetch_url(url)
            soup = _make_soup(resp.text)
            text = _extract_text(soup)
            title = _extract_title(soup)
            pages.append({
                "url": resp.url,
                "title": title,
                "text": text,
            })
            for a in soup.find_all("a", href=True):
                link = urljoin(resp.url, a["href"])
                link_parsed = urlparse(link)
                link_clean = link_parsed._replace(fragment="").geturl()
                if link_parsed.netloc == domain and link_clean not in visited:
                    queue.append(link_clean)
        except (BrowserAgentError, Exception):
            continue

    return {"domain": domain, "pages_crawled": len(pages), "pages": pages}


def _action_check_url(params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url", "")
    session = _get_session()
    try:
        resp = session.head(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return {
            "url": url,
            "final_url": resp.url,
            "exists": resp.status_code < 400,
            "status_code": resp.status_code,
        }
    except requests.RequestException as exc:
        return {
            "url": url,
            "exists": False,
            "status_code": None,
            "error": str(exc),
        }


def _action_research_bundle(params: dict[str, Any]) -> dict[str, Any]:
    queries = params.get("queries")
    if not queries or not isinstance(queries, list):
        raise BrowserAgentError("Missing or invalid queries parameter (expected a list)")
    if not all(isinstance(q, str) and q.strip() for q in queries):
        raise BrowserAgentError("All queries must be non-empty strings")

    max_per_query_raw = params.get("max_results_per_query", 5)
    try:
        max_per_query = int(max_per_query_raw)
    except (TypeError, ValueError):
        raise BrowserAgentError("max_results_per_query must be an integer")
    if max_per_query < 1:
        max_per_query = 1
    if max_per_query > MAX_RESULTS_CAP:
        max_per_query = MAX_RESULTS_CAP

    fetch_top = bool(params.get("fetch_top_pages", False))

    results: dict[str, Any] = {}
    for query in queries:
        q = query.strip()
        entry: dict[str, Any] = {}
        try:
            search_results = _ddg_search(q, max_per_query)
            entry["search_results"] = search_results
        except BrowserAgentError as exc:
            entry["search_results"] = []
            entry["search_error"] = str(exc)

        if fetch_top and entry.get("search_results"):
            top_url = entry["search_results"][0].get("url", "")
            if top_url:
                try:
                    page = _fetch_and_parse(top_url)
                    entry["top_page"] = {
                        "url": page["url"],
                        "title": page["title"],
                        "text": page["text"],
                    }
                except (BrowserAgentError, Exception) as exc:
                    entry["top_page"] = {"url": top_url, "error": str(exc)}

        results[q] = entry

    return {"results": results}


def _action_get_raw_html(params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url", "")
    resp = _fetch_url(url)
    return {"url": resp.url, "status_code": resp.status_code, "html": resp.text}


# --------------------------------------------------------------------------- #
# Action registry and parameter validation
# --------------------------------------------------------------------------- #
_REQUIRED_PARAMS: dict[str, list[str]] = {
    "web_search": ["query"],
    "multi_search": ["queries"],
    "fetch_page": ["url"],
    "fetch_multiple_pages": ["urls"],
    "extract_text": ["url"],
    "extract_links": ["url"],
    "extract_images": ["url"],
    "get_page_metadata": ["url"],
    "crawl_website": ["url"],
    "check_url": ["url"],
    "research_bundle": ["queries"],
    "get_raw_html": ["url"],
}

_ACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "web_search": _action_web_search,
    "multi_search": _action_multi_search,
    "fetch_page": _action_fetch_page,
    "fetch_multiple_pages": _action_fetch_multiple_pages,
    "extract_text": _action_extract_text,
    "extract_links": _action_extract_links,
    "extract_images": _action_extract_images,
    "get_page_metadata": _action_get_page_metadata,
    "crawl_website": _action_crawl_website,
    "check_url": _action_check_url,
    "research_bundle": _action_research_bundle,
    "get_raw_html": _action_get_raw_html,
}


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def execute(request_json: dict[str, Any]) -> dict[str, Any]:
    """Execute a browser/search action.

    Args:
        request_json: A dict with ``"action"`` (str) and ``"parameters"`` (dict).

    Returns:
        A JSON-compatible dict with ``"status"`` (``"success"`` | ``"error"``),
        ``"action"``, and either ``"data"`` or ``"message"``.
    """
    if isinstance(request_json, str):
        request_json = request_json.lstrip("﻿")
        try:
            request_json = json.loads(request_json)
        except json.JSONDecodeError as exc:
            return {"status": "error", "action": "unknown", "message": f"Invalid JSON: {exc}"}

    if not isinstance(request_json, dict):
        return {"status": "error", "action": "unknown", "message": "Request must be a JSON object"}

    action = request_json.get("action", "")
    if not action or not isinstance(action, str):
        return {"status": "error", "action": "unknown", "message": "Missing or invalid action field"}

    if action not in _ACTIONS:
        return {
            "status": "error",
            "action": action,
            "message": f"Unknown action: {action}. Available: {', '.join(sorted(_ACTIONS))}",
        }

    parameters = request_json.get("parameters", {})
    if not isinstance(parameters, dict):
        return {"status": "error", "action": action, "message": "parameters must be a JSON object"}

    required = _REQUIRED_PARAMS.get(action, [])
    for key in required:
        value = parameters.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return {"status": "error", "action": action, "message": f"Missing required parameter: {key}"}

    try:
        data = _ACTIONS[action](parameters)
        return {"status": "success", "action": action, "data": data}
    except BrowserAgentError as exc:
        return {"status": "error", "action": action, "message": str(exc)}
    except Exception as exc:
        return {"status": "error", "action": action, "message": f"Unexpected error: {exc}"}


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #
def _cli_main() -> None:
    """Handle command-line invocation: file arg, inline JSON arg, or piped stdin."""
    raw: Optional[str] = None

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if os.path.isfile(arg):
            with open(arg, "rb") as fh:
                raw = fh.read().decode("utf-8-sig")
        else:
            raw = arg
    elif not sys.stdin.isatty():
        raw = sys.stdin.buffer.read().decode("utf-8-sig")
    else:
        print(
            "Usage:\n"
            '  python browser_agent.py request.json\n'
            '  python browser_agent.py \'{"action":"web_search","parameters":{"query":"AI news"}}\'\n'
            '  echo \'{"action":"check_url","parameters":{"url":"https://example.com"}}\' '
            "| python browser_agent.py",
            file=sys.stderr,
        )
        sys.exit(2)

    raw = raw.strip().lstrip("﻿")
    try:
        request_data = json.loads(raw)
    except json.JSONDecodeError as exc:
        result = {"status": "error", "action": "unknown", "message": f"Invalid JSON input: {exc}"}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    result = execute(request_data)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    _cli_main()
