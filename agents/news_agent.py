"""news_agent.py — News retrieval plugin using NewsAPI (TOOL ONLY).

This module is a *pure tool*. It performs **no** analysis, summarization,
opinion generation, classification, sentiment analysis, ranking, reasoning,
or decision making. It only:

    1. Receives a JSON-compatible ``dict`` request.
    2. Calls NewsAPI (https://newsapi.org/v2).
    3. Collects the requested news data.
    4. Returns a JSON-compatible ``dict`` response.

All intelligence belongs to the calling "Brain Agent". The single public
entry point is :func:`execute`.

Dependencies (install once)::

    pip install requests python-dotenv

Configuration:
    * ``NEWS_API_KEY`` is read from the environment / a ``.env`` file
      (loaded automatically via python-dotenv). The key is never hardcoded.

CLI usage (handy for the Brain Agent to call as a subprocess)::

    python news_agent.py request.json
    python news_agent.py '{"action": "top_headlines", "parameters": {"country": "us"}}'
    '{"action":"get_sources","parameters":{}}' | python news_agent.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any, Callable, Optional

import requests
from dotenv import load_dotenv

__all__ = ["execute", "PLUGIN_INFO"]


# --------------------------------------------------------------------------- #
# Plugin metadata
# --------------------------------------------------------------------------- #
PLUGIN_INFO: dict[str, str] = {
    "name": "news_agent",
    "agent_name": "NewsAgent",
    "version": "1.0.0",
    "type": "tool",
    "input_format": "json",
    "output_format": "json",
    "entrypoint": "execute",
    "description": "News retrieval plugin using NewsAPI",
}


# --------------------------------------------------------------------------- #
# Configuration constants
# --------------------------------------------------------------------------- #
_BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))

# Load environment from the current working dir / parents, then fall back to a
# ``.env`` sitting next to this file (so the plugin works from any CWD).
load_dotenv()
load_dotenv(os.path.join(_BASE_DIR, ".env"), override=False)

NEWSAPI_BASE: str = "https://newsapi.org/v2"
REQUEST_TIMEOUT: int = 15  # seconds
DEFAULT_LIMIT: int = 20
MAX_PAGE_SIZE: int = 100  # NewsAPI hard cap for pageSize.
DEFAULT_COUNTRY: str = "us"

VALID_CATEGORIES: frozenset[str] = frozenset(
    {"business", "entertainment", "general", "health", "science", "sports", "technology"}
)
VALID_SORT_BY: frozenset[str] = frozenset({"relevancy", "popularity", "publishedAt"})


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class NewsAgentError(Exception):
    """Raised for any handled error whose message is safe to return.

    Covers parameter validation, missing API key, network failures, and
    NewsAPI-reported errors. These map to a structured ``status: error``
    response instead of crashing the tool.
    """


# --------------------------------------------------------------------------- #
# API key / HTTP session
# --------------------------------------------------------------------------- #
_API_KEY_CACHE: Optional[str] = None
_SESSION: Optional[requests.Session] = None


def _get_api_key() -> str:
    """Return the NewsAPI key from the environment.

    Raises:
        NewsAgentError: ``NEWS_API_KEY`` is not set.
    """
    global _API_KEY_CACHE
    if _API_KEY_CACHE is None:
        key = os.getenv("NEWS_API_KEY")
        if not key or not key.strip():
            raise NewsAgentError(
                "NEWS_API_KEY not found. Add it to your .env file."
            )
        _API_KEY_CACHE = key.strip()
    return _API_KEY_CACHE


def _get_session() -> requests.Session:
    """Return a cached :class:`requests.Session` with the API key header set."""
    global _SESSION
    if _SESSION is None:
        session = requests.Session()
        session.headers.update({"X-Api-Key": _get_api_key()})
        _SESSION = session
    return _SESSION


def _request(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    """Perform a GET against a NewsAPI endpoint and return the parsed JSON.

    ``None``-valued params are dropped. NewsAPI/network errors are converted
    into :class:`NewsAgentError` with a safe, human-readable message.

    Args:
        endpoint: Endpoint path, e.g. ``"top-headlines"`` or ``"everything"``.
        params: Query parameters (``None`` values are omitted).

    Raises:
        NewsAgentError: On network failure or a NewsAPI error response.
    """
    clean_params = {key: value for key, value in params.items() if value is not None}
    try:
        response = _get_session().get(
            f"{NEWSAPI_BASE}/{endpoint}",
            params=clean_params,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise NewsAgentError(f"Network error contacting NewsAPI: {exc}")

    try:
        payload = response.json()
    except ValueError:
        raise NewsAgentError(
            f"NewsAPI returned a non-JSON response (HTTP {response.status_code})"
        )

    if response.status_code != 200 or payload.get("status") == "error":
        message = payload.get("message") or (
            f"NewsAPI request failed (HTTP {response.status_code})"
        )
        raise NewsAgentError(message)

    return payload


# --------------------------------------------------------------------------- #
# Parameter helpers
# --------------------------------------------------------------------------- #
def _require(parameters: dict[str, Any], key: str) -> Any:
    """Return ``parameters[key]`` or raise if missing/blank."""
    value = parameters.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise NewsAgentError(f"Missing {key} parameter")
    return value


def _require_list(parameters: dict[str, Any], key: str) -> list[str]:
    """Return a validated non-empty list of non-blank strings."""
    value = parameters.get(key)
    if value is None:
        raise NewsAgentError(f"Missing {key} parameter")
    if not isinstance(value, list) or not value:
        raise NewsAgentError(f"Parameter '{key}' must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise NewsAgentError(f"Parameter '{key}' must contain non-empty strings")
    return value


def _optional_list(parameters: dict[str, Any], key: str) -> list[str]:
    """Return a validated list (possibly empty) of non-blank strings."""
    value = parameters.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise NewsAgentError(f"Parameter '{key}' must be a list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise NewsAgentError(f"Parameter '{key}' must contain non-empty strings")
    return value


def _get_limit(
    parameters: dict[str, Any], key: str = "limit", default: int = DEFAULT_LIMIT
) -> int:
    """Parse and clamp an integer ``limit``-style parameter to ``MAX_PAGE_SIZE``."""
    raw = parameters.get(key, default)
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        raise NewsAgentError(f"Parameter '{key}' must be an integer")
    if limit <= 0:
        raise NewsAgentError(f"Parameter '{key}' must be a positive integer")
    return min(limit, MAX_PAGE_SIZE)


def _validate_category(category: str) -> str:
    """Validate a NewsAPI category, returning it unchanged."""
    if category not in VALID_CATEGORIES:
        raise NewsAgentError(
            f"Invalid category '{category}'. Supported: "
            f"{', '.join(sorted(VALID_CATEGORIES))}"
        )
    return category


def _validate_sort_by(sort_by: str) -> str:
    """Validate a NewsAPI ``sortBy`` value, returning it unchanged."""
    if sort_by not in VALID_SORT_BY:
        raise NewsAgentError(
            f"Invalid sort_by '{sort_by}'. Supported: "
            f"{', '.join(sorted(VALID_SORT_BY))}"
        )
    return sort_by


def _validate_date(date_str: str) -> str:
    """Validate a ``YYYY-MM-DD`` date string, returning it unchanged."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise NewsAgentError(
            f"Invalid date '{date_str}', expected format YYYY-MM-DD"
        )
    return date_str


# --------------------------------------------------------------------------- #
# Data shaping (pure mapping — no interpretation)
# --------------------------------------------------------------------------- #
def _parse_article(article: dict[str, Any]) -> dict[str, Any]:
    """Map a raw NewsAPI article to the standard article dict (nulls -> "")."""
    source = article.get("source") or {}
    return {
        "title": article.get("title") or "",
        "source": source.get("name") or "",
        "author": article.get("author") or "",
        "description": article.get("description") or "",
        "url": article.get("url") or "",
        "image_url": article.get("urlToImage") or "",
        "published_at": article.get("publishedAt") or "",
        "content": article.get("content") or "",
    }


def _parse_source(source: dict[str, Any]) -> dict[str, Any]:
    """Map a raw NewsAPI source to a stable source dict (nulls -> "")."""
    return {
        "id": source.get("id") or "",
        "name": source.get("name") or "",
        "description": source.get("description") or "",
        "url": source.get("url") or "",
        "category": source.get("category") or "",
        "language": source.get("language") or "",
        "country": source.get("country") or "",
    }


def _data_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Standard ``count`` + ``data`` response fragment for list results."""
    return {"count": len(items), "data": items}


# --------------------------------------------------------------------------- #
# NewsAPI fetch helpers
# --------------------------------------------------------------------------- #
def _fetch_everything(
    query: str,
    limit: int,
    sort_by: str = "publishedAt",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    language: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Fetch articles from the ``/everything`` endpoint."""
    payload = _request(
        "everything",
        {
            "q": query,
            "pageSize": min(limit, MAX_PAGE_SIZE),
            "sortBy": sort_by,
            "from": from_date,
            "to": to_date,
            "language": language,
        },
    )
    articles = [_parse_article(item) for item in payload.get("articles", [])]
    return articles[:limit]


def _fetch_top_headlines(
    country: Optional[str] = None,
    category: Optional[str] = None,
    sources: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Fetch articles from the ``/top-headlines`` endpoint.

    NewsAPI forbids combining ``sources`` with ``country``/``category``; when
    ``sources`` is supplied the country/category filters are omitted.
    """
    params: dict[str, Any] = {"pageSize": min(limit, MAX_PAGE_SIZE), "q": query}
    if sources:
        params["sources"] = sources
    else:
        params["country"] = country
        params["category"] = category
    payload = _request("top-headlines", params)
    articles = [_parse_article(item) for item in payload.get("articles", [])]
    return articles[:limit]


# --------------------------------------------------------------------------- #
# Action handlers — each returns a response *fragment* merged into the base
# success envelope. None of these interpret, rank, or summarize content.
# --------------------------------------------------------------------------- #
def _action_top_headlines(parameters: dict[str, Any]) -> dict[str, Any]:
    """Top headlines for a country (optionally filtered by category)."""
    country = parameters.get("country", DEFAULT_COUNTRY)
    category = parameters.get("category")
    if category is not None:
        _validate_category(category)
    limit = _get_limit(parameters)
    articles = _fetch_top_headlines(country=country, category=category, limit=limit)
    return _data_response(articles)


def _action_search_news(parameters: dict[str, Any]) -> dict[str, Any]:
    """Search all articles for a single query."""
    query = _require(parameters, "query")
    limit = _get_limit(parameters)
    sort_by = _validate_sort_by(parameters.get("sort_by", "publishedAt"))
    articles = _fetch_everything(
        query, limit, sort_by=sort_by, language=parameters.get("language")
    )
    return _data_response(articles)


def _action_search_multiple_topics(parameters: dict[str, Any]) -> dict[str, Any]:
    """Fetch news for several topics, grouped by topic."""
    topics = _require_list(parameters, "topics")
    limit = _get_limit(parameters, key="limit_per_topic")
    results: dict[str, list[dict[str, Any]]] = {}
    total = 0
    for topic in topics:
        articles = _fetch_everything(topic, limit)
        results[topic] = articles
        total += len(articles)
    return {"total_articles": total, "topics": results}


def _action_search_multiple_queries(parameters: dict[str, Any]) -> dict[str, Any]:
    """Fetch news for several queries, grouped by query."""
    queries = _require_list(parameters, "queries")
    limit = _get_limit(parameters)
    results: dict[str, list[dict[str, Any]]] = {}
    total = 0
    for query in queries:
        articles = _fetch_everything(query, limit)
        results[query] = articles
        total += len(articles)
    return {"total_articles": total, "queries": results}


def _action_get_latest_news(parameters: dict[str, Any]) -> dict[str, Any]:
    """Latest top headlines for a country (defaults to ``us``)."""
    country = parameters.get("country", DEFAULT_COUNTRY)
    limit = _get_limit(parameters)
    articles = _fetch_top_headlines(country=country, limit=limit)
    return _data_response(articles)


def _action_get_category_news(parameters: dict[str, Any]) -> dict[str, Any]:
    """Top headlines for a specific category and country."""
    category = _validate_category(_require(parameters, "category"))
    country = parameters.get("country", DEFAULT_COUNTRY)
    limit = _get_limit(parameters)
    articles = _fetch_top_headlines(country=country, category=category, limit=limit)
    return _data_response(articles)


def _action_get_source_news(parameters: dict[str, Any]) -> dict[str, Any]:
    """Top headlines from a specific source (e.g. ``bbc-news``)."""
    source = _require(parameters, "source")
    limit = _get_limit(parameters)
    articles = _fetch_top_headlines(sources=source, limit=limit)
    return _data_response(articles)


def _action_get_sources(parameters: dict[str, Any]) -> dict[str, Any]:
    """List available NewsAPI sources (optionally filtered)."""
    category = parameters.get("category")
    if category is not None:
        _validate_category(category)
    payload = _request(
        "top-headlines/sources",
        {
            "category": category,
            "language": parameters.get("language"),
            "country": parameters.get("country"),
        },
    )
    sources = [_parse_source(item) for item in payload.get("sources", [])]
    return _data_response(sources)


def _action_search_date_range(parameters: dict[str, Any]) -> dict[str, Any]:
    """Search articles for a query within a date range (``YYYY-MM-DD``)."""
    query = _require(parameters, "query")
    from_date = parameters.get("from_date")
    to_date = parameters.get("to_date")
    if from_date is not None:
        _validate_date(from_date)
    if to_date is not None:
        _validate_date(to_date)
    limit = _get_limit(parameters)
    sort_by = _validate_sort_by(parameters.get("sort_by", "publishedAt"))
    articles = _fetch_everything(
        query,
        limit,
        sort_by=sort_by,
        from_date=from_date,
        to_date=to_date,
        language=parameters.get("language"),
    )
    return _data_response(articles)


def _action_search_combined(parameters: dict[str, Any]) -> dict[str, Any]:
    """Aggregate news across topics, categories, and sources in one request."""
    topics = _optional_list(parameters, "topics")
    categories = _optional_list(parameters, "categories")
    sources = _optional_list(parameters, "sources")
    if not (topics or categories or sources):
        raise NewsAgentError(
            "Provide at least one of: topics, categories, sources"
        )
    country = parameters.get("country", DEFAULT_COUNTRY)
    limit = _get_limit(parameters)

    results: dict[str, dict[str, list[dict[str, Any]]]] = {
        "topics": {},
        "categories": {},
        "sources": {},
    }
    for topic in topics:
        results["topics"][topic] = _fetch_everything(topic, limit)
    for category in categories:
        _validate_category(category)
        results["categories"][category] = _fetch_top_headlines(
            country=country, category=category, limit=limit
        )
    for source in sources:
        results["sources"][source] = _fetch_top_headlines(sources=source, limit=limit)

    return {"results": results}


# Required parameters per action, validated *before* any network call so a
# malformed request fails fast. Handlers re-validate (and do deeper checks) so
# they remain safe if called directly.
_REQUIRED_PARAMS: dict[str, list[str]] = {
    "search_news": ["query"],
    "search_multiple_topics": ["topics"],
    "search_multiple_queries": ["queries"],
    "get_category_news": ["category"],
    "get_source_news": ["source"],
    "search_date_range": ["query"],
}


# Action registry: maps an action name to its handler.
_ACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "top_headlines": _action_top_headlines,
    "search_news": _action_search_news,
    "search_multiple_topics": _action_search_multiple_topics,
    "search_multiple_queries": _action_search_multiple_queries,
    "get_latest_news": _action_get_latest_news,
    "get_category_news": _action_get_category_news,
    "get_source_news": _action_get_source_news,
    "get_sources": _action_get_sources,
    "search_date_range": _action_search_date_range,
    "search_combined": _action_search_combined,
}


# --------------------------------------------------------------------------- #
# Response builder
# --------------------------------------------------------------------------- #
def _error(action: Optional[str], message: str) -> dict[str, Any]:
    """Build a structured error response."""
    return {"status": "error", "action": action, "message": message}


# --------------------------------------------------------------------------- #
# Public interface
# --------------------------------------------------------------------------- #
def execute(request_json: dict) -> dict:
    """Single public entry point — route a JSON request to a NewsAPI operation.

    Validates input, dispatches to the matching read-only handler, and always
    returns a JSON-compatible ``dict``. It never raises; every error becomes a
    ``{"status": "error", ...}`` response.

    Args:
        request_json: A request dict (a JSON string is also accepted and parsed)
            of the form ``{"action": <str>, "parameters": <dict>}``.

    Returns:
        On success a ``{"status": "success", "action": <str>, ...}`` envelope
        whose remaining keys depend on the action (``count``/``data``,
        ``total_articles``/``topics``, ``results``, ...). On failure,
        ``{"status": "error", "action": <str|None>, "message": <str>}``.
    """
    action: Optional[str] = None
    try:
        # Accept a raw JSON string for convenience, though dict is the contract.
        # ``lstrip`` drops a leading BOM that some shells (PowerShell) prepend.
        if isinstance(request_json, str):
            try:
                request_json = json.loads(request_json.lstrip("\ufeff"))
            except json.JSONDecodeError as exc:
                return _error(None, f"Invalid JSON input: {exc}")

        if not isinstance(request_json, dict):
            return _error(None, "Request must be a JSON object (dict)")

        action = request_json.get("action")
        if not action or not isinstance(action, str):
            return _error(action, "Missing or invalid 'action' field")

        handler = _ACTIONS.get(action)
        if handler is None:
            return _error(action, "Unsupported action")

        parameters = request_json.get("parameters", {})
        if parameters is None:
            parameters = {}
        if not isinstance(parameters, dict):
            return _error(action, "'parameters' must be a JSON object")

        # Validate required parameters before any network call (router step 3).
        for required_key in _REQUIRED_PARAMS.get(action, []):
            _require(parameters, required_key)

        result = handler(parameters)
        return {"status": "success", "action": action, **result}

    except NewsAgentError as exc:
        return _error(action, str(exc))
    except Exception as exc:  # noqa: BLE001 - tool must never crash the Brain.
        return _error(action, f"Unexpected error: {exc}")


# --------------------------------------------------------------------------- #
# CLI shim — accept a JSON request from a file, an argument, or stdin.
# --------------------------------------------------------------------------- #
def _read_stdin() -> str:
    """Read stdin as bytes and decode with ``utf-8-sig`` to strip any BOM.

    PowerShell prepends a UTF-8 BOM when piping to a native process, which
    would otherwise make the JSON unparseable; ``utf-8-sig`` removes it.
    """
    return sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")


def _print_usage() -> None:
    """Print CLI usage to stderr (shown when run on a TTY with no input)."""
    sys.stderr.write(
        "news_agent - News retrieval tool using NewsAPI (JSON in, JSON out)\n\n"
        "Provide a JSON request one of these ways:\n\n"
        "  1) From a file (most reliable on Windows/PowerShell):\n"
        "       python news_agent.py request.json\n\n"
        "  2) Piped via stdin:\n"
        "       '{\"action\":\"top_headlines\",\"parameters\":{\"country\":\"us\"}}'"
        " | python news_agent.py\n\n"
        "  3) As one argument with escaped quotes (PowerShell):\n"
        "       python news_agent.py '{\\\"action\\\":\\\"get_sources\\\","
        "\\\"parameters\\\":{}}'\n\n"
        "Actions: " + ", ".join(sorted(_ACTIONS)) + "\n"
    )


def _main(argv: list[str]) -> int:
    """Run a single request from the command line and print the JSON result.

    Input source (first match wins):
        1. ``argv[1]`` naming an existing file -> read JSON from that file.
        2. ``argv[1]`` otherwise -> treat it as a JSON string.
        3. Piped stdin -> read the request from stdin.
        4. Interactive terminal with no input -> print usage and exit.
    """
    if len(argv) > 1:
        arg = argv[1]
        if os.path.isfile(arg):
            with open(arg, "r", encoding="utf-8-sig") as handle:
                raw = handle.read()
        else:
            raw = arg
    elif not sys.stdin.isatty():
        raw = _read_stdin()
    else:
        _print_usage()
        return 2

    if not raw or not raw.strip():
        print(json.dumps(_error(None, "No JSON request provided")))
        return 1

    response = execute(raw)
    print(json.dumps(response, indent=2, ensure_ascii=False))
    return 0 if response.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
