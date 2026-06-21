"""youtube_agent.py — YouTube search and playback plugin (TOOL ONLY).

This module is a *pure tool*. It performs **no** analysis, summarization,
recommendations, reasoning, intent detection, or decision making. It only:

    1. Receives a JSON-compatible ``dict`` request.
    2. Searches YouTube or retrieves video/channel/playlist metadata via yt-dlp.
    3. Optionally opens URLs in the default browser.
    4. Returns a JSON-compatible ``dict`` response.

All intelligence belongs to the calling "Brain Agent". The single public
entry point is :func:`execute`.

Dependencies (install once)::

    pip install yt-dlp

No API keys required.

CLI usage::

    python youtube_agent.py request.json
    python youtube_agent.py '{"action": "search_videos", "parameters": {"query": "Python tutorial", "limit": 5}}'
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from typing import Any, Callable, Optional

import yt_dlp

__all__ = ["execute", "PLUGIN_INFO"]


# --------------------------------------------------------------------------- #
# Plugin metadata
# --------------------------------------------------------------------------- #
PLUGIN_INFO: dict[str, str] = {
    "name": "youtube_agent",
    "agent_name": "YouTubeAgent",
    "version": "1.0.0",
    "type": "tool",
    "input_format": "json",
    "output_format": "json",
    "entrypoint": "execute",
    "description": "YouTube search and playback plugin",
}


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
DEFAULT_LIMIT: int = 10
MAX_LIMIT: int = 50
YOUTUBE_BASE: str = "https://www.youtube.com"


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class YouTubeAgentError(Exception):
    """Raised for any handled error whose message is safe to return."""


# --------------------------------------------------------------------------- #
# yt-dlp helpers
# --------------------------------------------------------------------------- #
def _base_opts() -> dict[str, Any]:
    """Return common yt-dlp options shared by all extractors."""
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "no_color": True,
        "geo_bypass": True,
    }


def _flat_opts(limit: int) -> dict[str, Any]:
    """Options for flat (metadata-only) extraction with a result cap."""
    opts = _base_opts()
    opts["extract_flat"] = True
    opts["playlistend"] = limit
    return opts


def _clamp_limit(params: dict[str, Any], key: str = "limit") -> int:
    """Parse and clamp a limit parameter."""
    raw = params.get(key, DEFAULT_LIMIT)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise YouTubeAgentError(f"Parameter '{key}' must be an integer")
    if n < 1:
        n = 1
    if n > MAX_LIMIT:
        n = MAX_LIMIT
    return n


def _format_duration(seconds: Any) -> str:
    """Convert numeric seconds to HH:MM:SS or MM:SS string."""
    if seconds is None:
        return ""
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return str(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_date(raw: Any) -> str:
    """Convert YYYYMMDD to YYYY-MM-DD, or return as-is."""
    if not raw or not isinstance(raw, str):
        return str(raw) if raw else ""
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw


def _best_thumbnail(entry: dict[str, Any]) -> str:
    """Pick the best thumbnail URL from an entry."""
    thumb = entry.get("thumbnail")
    if thumb:
        return thumb
    thumbnails = entry.get("thumbnails")
    if thumbnails and isinstance(thumbnails, list):
        best = max(thumbnails, key=lambda t: t.get("width", 0) * t.get("height", 0))
        return best.get("url", "")
    vid = entry.get("id", "")
    if vid:
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return ""


def _parse_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Normalise a yt-dlp entry into the standard video format."""
    vid = entry.get("id", "")
    return {
        "video_id": vid,
        "title": entry.get("title", ""),
        "channel": entry.get("channel") or entry.get("uploader", ""),
        "channel_url": entry.get("channel_url") or entry.get("uploader_url", ""),
        "duration": _format_duration(entry.get("duration")),
        "duration_seconds": entry.get("duration"),
        "view_count": entry.get("view_count"),
        "published": _format_date(entry.get("upload_date")),
        "url": entry.get("url") or entry.get("webpage_url") or f"{YOUTUBE_BASE}/watch?v={vid}",
        "thumbnail": _best_thumbnail(entry),
    }


def _extract(url: str, opts: dict[str, Any]) -> dict[str, Any]:
    """Run yt-dlp extraction with the given options."""
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc)
        if "HTTP Error 404" in msg or "not found" in msg.lower():
            raise YouTubeAgentError("Video/page not found")
        raise YouTubeAgentError(f"yt-dlp extraction failed: {msg}")
    except Exception as exc:
        raise YouTubeAgentError(f"yt-dlp error: {exc}")
    if result is None:
        raise YouTubeAgentError("No results returned")
    return result


def _search(query: str, limit: int) -> list[dict[str, Any]]:
    """Search YouTube and return normalised video entries."""
    opts = _flat_opts(limit)
    result = _extract(f"ytsearch{limit}:{query}", opts)
    entries = result.get("entries") or []
    return [_parse_entry(e) for e in entries if e]


def _video_url(params: dict[str, Any]) -> str:
    """Resolve a video URL from either video_url or video_id parameter."""
    url = str(params.get("video_url", "")).strip()
    if url:
        return url
    vid = str(params.get("video_id", "")).strip()
    if vid:
        return f"{YOUTUBE_BASE}/watch?v={vid}"
    raise YouTubeAgentError("Missing video_url or video_id parameter")


def _open_browser(url: str) -> None:
    """Open *url* in the default browser."""
    try:
        webbrowser.open(url)
    except Exception as exc:
        raise YouTubeAgentError(f"Failed to open browser: {exc}")


# --------------------------------------------------------------------------- #
# Action handlers
# --------------------------------------------------------------------------- #
def _action_search_videos(params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("query", "")).strip()
    if not query:
        raise YouTubeAgentError("Missing query parameter")
    limit = _clamp_limit(params)
    videos = _search(query, limit)
    return {"count": len(videos), "videos": videos}


def _action_search_multiple(params: dict[str, Any]) -> dict[str, Any]:
    queries = params.get("queries")
    if not queries or not isinstance(queries, list):
        raise YouTubeAgentError("Missing or invalid queries parameter (expected a list)")
    if not all(isinstance(q, str) and q.strip() for q in queries):
        raise YouTubeAgentError("All queries must be non-empty strings")
    limit = _clamp_limit(params)

    results: dict[str, Any] = {}
    for query in queries:
        q = query.strip()
        try:
            results[q] = _search(q, limit)
        except YouTubeAgentError as exc:
            results[q] = {"error": str(exc)}
    return {"results": results}


def _action_get_video_details(params: dict[str, Any]) -> dict[str, Any]:
    url = _video_url(params)
    opts = _base_opts()
    result = _extract(url, opts)
    video = _parse_entry(result)
    video["description"] = result.get("description", "")
    video["like_count"] = result.get("like_count")
    video["comment_count"] = result.get("comment_count")
    video["categories"] = result.get("categories", [])
    video["tags"] = result.get("tags", [])
    return {"video": video}


def _action_play_video(params: dict[str, Any]) -> dict[str, Any]:
    url = _video_url(params)
    opts = _flat_opts(1)
    result = _extract(url, opts)
    video = _parse_entry(result)
    _open_browser(video["url"])
    return {"message": "Video opened in browser", "video": video}


def _action_search_and_play(params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("query", "")).strip()
    if not query:
        raise YouTubeAgentError("Missing query parameter")
    videos = _search(query, 1)
    if not videos:
        raise YouTubeAgentError("No videos found")
    video = videos[0]
    _open_browser(video["url"])
    return {"message": "First result opened in browser", "video": video}


def _action_open_channel(params: dict[str, Any]) -> dict[str, Any]:
    url = str(params.get("channel_url", "")).strip()
    if not url:
        raise YouTubeAgentError("Missing channel_url parameter")
    _open_browser(url)
    return {"message": "Channel opened in browser", "url": url}


def _action_get_channel_videos(params: dict[str, Any]) -> dict[str, Any]:
    url = str(params.get("channel_url", "")).strip()
    if not url:
        raise YouTubeAgentError("Missing channel_url parameter")
    if not url.endswith("/videos"):
        url = url.rstrip("/") + "/videos"
    limit = _clamp_limit(params)
    opts = _flat_opts(limit)
    result = _extract(url, opts)
    entries = result.get("entries") or []
    videos = [_parse_entry(e) for e in entries if e]
    channel_name = result.get("channel") or result.get("uploader", "")
    return {"channel": channel_name, "count": len(videos), "videos": videos}


def _action_get_trending(params: dict[str, Any]) -> dict[str, Any]:
    country = str(params.get("country", "US")).strip().upper()
    limit = _clamp_limit(params)
    url = f"{YOUTUBE_BASE}/feed/trending?gl={country}"
    opts = _flat_opts(limit)
    try:
        result = _extract(url, opts)
        entries = result.get("entries") or []
        videos = [_parse_entry(e) for e in entries if e]
    except YouTubeAgentError:
        videos = _search(f"trending in {country}", limit)
    return {"country": country, "count": len(videos), "videos": videos}


def _action_open_playlist(params: dict[str, Any]) -> dict[str, Any]:
    url = str(params.get("playlist_url", "")).strip()
    if not url:
        raise YouTubeAgentError("Missing playlist_url parameter")
    _open_browser(url)
    return {"message": "Playlist opened in browser", "url": url}


def _action_get_playlist_videos(params: dict[str, Any]) -> dict[str, Any]:
    url = str(params.get("playlist_url", "")).strip()
    if not url:
        raise YouTubeAgentError("Missing playlist_url parameter")
    limit = _clamp_limit(params)
    opts = _flat_opts(limit)
    result = _extract(url, opts)
    entries = result.get("entries") or []
    videos = [_parse_entry(e) for e in entries if e]
    playlist_title = result.get("title", "")
    return {"playlist": playlist_title, "count": len(videos), "videos": videos}


def _action_open_url(params: dict[str, Any]) -> dict[str, Any]:
    url = str(params.get("url", "")).strip()
    if not url:
        raise YouTubeAgentError("Missing url parameter")
    _open_browser(url)
    return {"message": "URL opened in browser", "url": url}


def _action_search_bundle(params: dict[str, Any]) -> dict[str, Any]:
    queries = params.get("queries")
    if not queries or not isinstance(queries, list):
        raise YouTubeAgentError("Missing or invalid queries parameter (expected a list)")
    if not all(isinstance(q, str) and q.strip() for q in queries):
        raise YouTubeAgentError("All queries must be non-empty strings")
    limit = _clamp_limit(params)

    results: dict[str, Any] = {}
    for query in queries:
        q = query.strip()
        try:
            videos = _search(q, limit)
            results[q] = {"count": len(videos), "videos": videos}
        except YouTubeAgentError as exc:
            results[q] = {"error": str(exc)}
    return {"results": results}


# --------------------------------------------------------------------------- #
# Action registry and parameter validation
# --------------------------------------------------------------------------- #
_REQUIRED_PARAMS: dict[str, list[str]] = {
    "search_videos": ["query"],
    "search_multiple": ["queries"],
    "get_video_details": [],
    "play_video": [],
    "search_and_play": ["query"],
    "open_channel": ["channel_url"],
    "get_channel_videos": ["channel_url"],
    "get_trending": [],
    "open_playlist": ["playlist_url"],
    "get_playlist_videos": ["playlist_url"],
    "open_url": ["url"],
    "search_bundle": ["queries"],
}

_ACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "search_videos": _action_search_videos,
    "search_multiple": _action_search_multiple,
    "get_video_details": _action_get_video_details,
    "play_video": _action_play_video,
    "search_and_play": _action_search_and_play,
    "open_channel": _action_open_channel,
    "get_channel_videos": _action_get_channel_videos,
    "get_trending": _action_get_trending,
    "open_playlist": _action_open_playlist,
    "get_playlist_videos": _action_get_playlist_videos,
    "open_url": _action_open_url,
    "search_bundle": _action_search_bundle,
}


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def execute(request_json: dict[str, Any]) -> dict[str, Any]:
    """Execute a YouTube search or playback action.

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
    except YouTubeAgentError as exc:
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
            '  python youtube_agent.py request.json\n'
            '  python youtube_agent.py \'{"action":"search_videos","parameters":{"query":"Python"}}\'\n'
            '  echo \'{"action":"search_videos","parameters":{"query":"AI"}}\' '
            "| python youtube_agent.py",
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
