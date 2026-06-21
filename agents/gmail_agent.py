"""gmail_agent.py — Gmail retrieval and search plugin (TOOL ONLY).

This module is a *pure tool*. It performs **no** analysis, reasoning,
summarization, classification, intent detection, or decision making. It only:

    1. Receives a JSON-compatible ``dict`` request.
    2. Performs read-only Gmail API operations.
    3. Returns a JSON-compatible ``dict`` response.

All intelligence belongs to the calling "Brain Agent". The single public
entry point is :func:`execute`.

Dependencies (install once)::

    pip install google-api-python-client google-auth google-auth-oauthlib

Authentication:
    * Expects an OAuth *installed app* ``credentials.json`` in the working dir.
    * On first run a browser window opens for consent and ``token.json`` is
      written. Subsequent runs reuse ``token.json`` and refresh it silently.

CLI usage (handy for the Brain Agent to call as a subprocess)::

    python gmail_agent.py '{"action": "get_latest_emails", "parameters": {"limit": 5}}'
    echo '{"action": "count_emails", "parameters": {"query": "is:unread"}}' | python gmail_agent.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from google.auth.exceptions import GoogleAuthError, RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

__all__ = ["execute", "PLUGIN_INFO"]


# --------------------------------------------------------------------------- #
# Plugin metadata
# --------------------------------------------------------------------------- #
PLUGIN_INFO: dict[str, str] = {
    "name": "gmail_agent",
    "agent_name": "GmailAgent",
    "version": "1.0.0",
    "type": "tool",
    "input_format": "json",
    "output_format": "json",
    "entrypoint": "execute",
    "description": "Gmail retrieval and search plugin",
}


# --------------------------------------------------------------------------- #
# Configuration constants
# --------------------------------------------------------------------------- #
# Read-only scope is sufficient for every supported action (all are reads).
SCOPES: list[str] = ["https://www.googleapis.com/auth/gmail.readonly"]

# Resolve credential paths relative to this file so the agent works regardless
# of the caller's current working directory.
_BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE: str = os.path.join(_BASE_DIR, "credentials.json")
TOKEN_FILE: str = os.path.join(_BASE_DIR, "token.json")

USER_ID: str = "me"
DEFAULT_LIMIT: int = 20
MAX_LIMIT: int = 500  # Gmail's per-page maximum for messages.list.
GMAIL_PAGE_SIZE: int = 500

# Headers requested when listing messages in the lightweight "metadata" format.
METADATA_HEADERS: list[str] = ["From", "To", "Subject", "Date"]


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class GmailAgentError(Exception):
    """Raised for request-validation problems (bad/missing parameters).

    These map to a structured ``status: error`` response rather than crashing.
    """


# --------------------------------------------------------------------------- #
# Authentication / service construction
# --------------------------------------------------------------------------- #
_SERVICE_CACHE: Optional[Any] = None
_SERVICE_LOCK = threading.Lock()


def _save_token(creds: Credentials) -> None:
    """Persist OAuth credentials to :data:`TOKEN_FILE` as JSON."""
    with open(TOKEN_FILE, "w", encoding="utf-8") as handle:
        handle.write(creds.to_json())


def _get_credentials() -> Credentials:
    """Load, refresh, or interactively obtain OAuth2 credentials.

    Order of operations:
        1. Reuse ``token.json`` if present and valid.
        2. Silently refresh it if expired but a refresh token exists.
        3. Otherwise run the installed-app consent flow and store a new token.

    Returns:
        Valid :class:`google.oauth2.credentials.Credentials`.

    Raises:
        FileNotFoundError: ``credentials.json`` is missing when a fresh
            interactive login is required.
        RefreshError / GoogleAuthError: The OAuth flow itself failed.
    """
    creds: Optional[Credentials] = None

    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except (ValueError, json.JSONDecodeError):
            # Corrupt/incompatible token file — discard and re-authenticate.
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            return creds
        except RefreshError:
            # Refresh token revoked/expired — fall through to full re-auth.
            creds = None

    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"OAuth client file not found: {CREDENTIALS_FILE}"
        )

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    _save_token(creds)
    return creds


def _get_service() -> Any:
    """Return a cached, authenticated Gmail API service client."""
    global _SERVICE_CACHE
    if _SERVICE_CACHE is not None:
        return _SERVICE_CACHE
    with _SERVICE_LOCK:
        if _SERVICE_CACHE is None:
            creds = _get_credentials()
            _SERVICE_CACHE = build(
                "gmail", "v1", credentials=creds, cache_discovery=False
            )
        return _SERVICE_CACHE


# --------------------------------------------------------------------------- #
# Parameter helpers
# --------------------------------------------------------------------------- #
def _require(parameters: dict[str, Any], key: str) -> Any:
    """Return ``parameters[key]`` or raise if missing/blank.

    Raises:
        GmailAgentError: The key is absent, ``None``, or an empty string.
    """
    value = parameters.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise GmailAgentError(f"Missing {key} parameter")
    return value


def _get_limit(parameters: dict[str, Any], default: int = DEFAULT_LIMIT) -> int:
    """Parse and clamp the optional ``limit`` parameter.

    Raises:
        GmailAgentError: ``limit`` is present but not a positive integer.
    """
    raw = parameters.get("limit", default)
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        raise GmailAgentError("Parameter 'limit' must be an integer")
    if limit <= 0:
        raise GmailAgentError("Parameter 'limit' must be a positive integer")
    return min(limit, MAX_LIMIT)


def _to_gmail_date(date_str: str, add_day: bool = False) -> str:
    """Convert ``YYYY-MM-DD`` to Gmail's ``YYYY/MM/DD`` query format.

    Args:
        date_str: Date in ISO ``YYYY-MM-DD`` form.
        add_day: If ``True``, add one day. Used to make ``before:`` ranges
            inclusive of the end date (Gmail's ``before:`` is exclusive).

    Raises:
        GmailAgentError: ``date_str`` is not a valid ``YYYY-MM-DD`` date.
    """
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise GmailAgentError(
            f"Invalid date '{date_str}', expected format YYYY-MM-DD"
        )
    if add_day:
        parsed += timedelta(days=1)
    return parsed.strftime("%Y/%m/%d")


# --------------------------------------------------------------------------- #
# Gmail data extraction (pure parsing — no interpretation)
# --------------------------------------------------------------------------- #
def _get_header(headers: list[dict[str, str]], name: str) -> str:
    """Return the value of header ``name`` (case-insensitive), or ``""``."""
    target = name.lower()
    for header in headers:
        if header.get("name", "").lower() == target:
            return header.get("value", "")
    return ""


def _decode_base64url(data: str) -> str:
    """Decode a Gmail base64url body part to a UTF-8 string."""
    if not data:
        return ""
    decoded = base64.urlsafe_b64decode(data.encode("utf-8"))
    return decoded.decode("utf-8", errors="replace")


def _find_part_body(payload: dict[str, Any], mime_type: str) -> str:
    """Recursively find the first body part matching ``mime_type``."""
    if payload.get("mimeType") == mime_type:
        data = payload.get("body", {}).get("data")
        if data:
            return _decode_base64url(data)
    for part in payload.get("parts", []) or []:
        found = _find_part_body(part, mime_type)
        if found:
            return found
    return ""


def _extract_body(payload: dict[str, Any]) -> str:
    """Extract the message body, preferring ``text/plain`` over ``text/html``."""
    plain = _find_part_body(payload, "text/plain")
    if plain:
        return plain
    return _find_part_body(payload, "text/html")


def _extract_attachments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect attachment metadata (filename, mime type, id, size)."""
    attachments: list[dict[str, Any]] = []

    def walk(part: dict[str, Any]) -> None:
        filename = part.get("filename")
        body = part.get("body", {})
        if filename:
            attachments.append(
                {
                    "filename": filename,
                    "mime_type": part.get("mimeType", ""),
                    "attachment_id": body.get("attachmentId", ""),
                    "size": body.get("size", 0),
                }
            )
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    return attachments


def _parse_message(
    message: dict[str, Any],
    include_body: bool = False,
    include_attachments: bool = False,
) -> dict[str, Any]:
    """Map a raw Gmail message resource to the standard email dict.

    Args:
        message: Raw message resource from the Gmail API.
        include_body: Include the decoded ``body`` field (needs full format).
        include_attachments: Include an ``attachments`` list (needs full format).
    """
    payload = message.get("payload", {}) or {}
    headers = payload.get("headers", []) or []

    email: dict[str, Any] = {
        "id": message.get("id", ""),
        "thread_id": message.get("threadId", ""),
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "subject": _get_header(headers, "Subject"),
        "date": _get_header(headers, "Date"),
        "snippet": message.get("snippet", ""),
        "label_ids": message.get("labelIds", []) or [],
    }
    if include_body:
        email["body"] = _extract_body(payload)
    if include_attachments:
        email["attachments"] = _extract_attachments(payload)
    return email


# --------------------------------------------------------------------------- #
# Gmail API access helpers
# --------------------------------------------------------------------------- #
def _list_message_ids(
    service: Any,
    query: Optional[str] = None,
    label_ids: Optional[list[str]] = None,
    limit: Optional[int] = None,
) -> list[str]:
    """List message IDs matching a query/labels, honoring an optional limit.

    When ``limit`` is ``None`` every matching message is paginated (used for an
    accurate ``count_emails``); otherwise pagination stops once ``limit`` IDs
    are collected. Results preserve Gmail's newest-first ordering.
    """
    ids: list[str] = []
    page_token: Optional[str] = None

    while True:
        page_size = GMAIL_PAGE_SIZE
        if limit is not None:
            remaining = limit - len(ids)
            if remaining <= 0:
                break
            page_size = min(GMAIL_PAGE_SIZE, remaining)

        response = (
            service.users()
            .messages()
            .list(
                userId=USER_ID,
                q=query or "",
                labelIds=label_ids or [],
                maxResults=page_size,
                pageToken=page_token,
            )
            .execute()
        )

        ids.extend(item["id"] for item in response.get("messages", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
        if limit is not None and len(ids) >= limit:
            break

    return ids


def _get_message(service: Any, message_id: str, full: bool = False) -> dict[str, Any]:
    """Fetch a single message in ``metadata`` (default) or ``full`` format."""
    if full:
        return (
            service.users()
            .messages()
            .get(userId=USER_ID, id=message_id, format="full")
            .execute()
        )
    return (
        service.users()
        .messages()
        .get(
            userId=USER_ID,
            id=message_id,
            format="metadata",
            metadataHeaders=METADATA_HEADERS,
        )
        .execute()
    )


def _fetch_emails(
    service: Any,
    message_ids: list[str],
    include_body: bool = False,
    include_attachments: bool = False,
) -> list[dict[str, Any]]:
    """Fetch and parse a list of message IDs into standard email dicts."""
    need_full = include_body or include_attachments
    emails: list[dict[str, Any]] = []
    for message_id in message_ids:
        raw = _get_message(service, message_id, full=need_full)
        emails.append(_parse_message(raw, include_body, include_attachments))
    return emails


# --------------------------------------------------------------------------- #
# Action handlers — each returns a list[email] (or an int for count_emails).
# None of these interpret content; they only read, filter, and shape data.
# --------------------------------------------------------------------------- #
def _action_get_latest_emails(service: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the most recent inbox emails."""
    limit = _get_limit(parameters)
    ids = _list_message_ids(service, label_ids=["INBOX"], limit=limit)
    return _fetch_emails(service, ids)


def _action_get_unread_emails(service: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Return unread emails."""
    limit = _get_limit(parameters)
    ids = _list_message_ids(service, label_ids=["UNREAD"], limit=limit)
    return _fetch_emails(service, ids)


def _action_search_sender(service: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Return emails from a given sender."""
    sender = _require(parameters, "sender")
    limit = _get_limit(parameters)
    ids = _list_message_ids(service, query=f"from:({sender})", limit=limit)
    return _fetch_emails(service, ids)


def _action_search_subject(service: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Return emails whose subject matches the given text."""
    subject = _require(parameters, "subject")
    limit = _get_limit(parameters)
    ids = _list_message_ids(service, query=f"subject:({subject})", limit=limit)
    return _fetch_emails(service, ids)


def _action_search_date_range(service: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Return emails within an inclusive ``start_date``..``end_date`` range."""
    start_date = _require(parameters, "start_date")
    end_date = _require(parameters, "end_date")
    limit = _get_limit(parameters)
    after = _to_gmail_date(start_date)
    before = _to_gmail_date(end_date, add_day=True)  # inclusive end date
    ids = _list_message_ids(service, query=f"after:{after} before:{before}", limit=limit)
    return _fetch_emails(service, ids)


def _action_search_gmail_query(service: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Return emails matching a raw Gmail search query string."""
    query = _require(parameters, "query")
    limit = _get_limit(parameters)
    ids = _list_message_ids(service, query=query, limit=limit)
    return _fetch_emails(service, ids)


def _action_get_email_by_id(service: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a single full email (with body and attachments) by message ID."""
    message_id = _require(parameters, "message_id")
    raw = _get_message(service, message_id, full=True)
    return [_parse_message(raw, include_body=True, include_attachments=True)]


def _action_get_attachments(service: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Return emails that have attachments, with attachment metadata."""
    limit = _get_limit(parameters)
    ids = _list_message_ids(service, query="has:attachment", limit=limit)
    return _fetch_emails(service, ids, include_attachments=True)


def _action_count_emails(service: Any, parameters: dict[str, Any]) -> int:
    """Return the estimated number of emails matching a Gmail query.

    Uses Gmail's ``resultSizeEstimate`` for a single API call instead of
    paginating through every matching message.
    """
    query = _require(parameters, "query")
    response = (
        service.users()
        .messages()
        .list(userId=USER_ID, q=query, maxResults=1)
        .execute()
    )
    return response.get("resultSizeEstimate", 0)


def _action_get_starred_emails(service: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Return starred emails."""
    limit = _get_limit(parameters)
    ids = _list_message_ids(service, label_ids=["STARRED"], limit=limit)
    return _fetch_emails(service, ids)


def _action_get_sent_emails(service: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Return sent emails."""
    limit = _get_limit(parameters)
    ids = _list_message_ids(service, label_ids=["SENT"], limit=limit)
    return _fetch_emails(service, ids)


def _action_get_important_emails(service: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Return emails marked Important."""
    limit = _get_limit(parameters)
    ids = _list_message_ids(service, label_ids=["IMPORTANT"], limit=limit)
    return _fetch_emails(service, ids)


def _action_get_drafts(service: Any, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Return draft emails."""
    limit = _get_limit(parameters)
    response = (
        service.users()
        .drafts()
        .list(userId=USER_ID, maxResults=min(limit, MAX_LIMIT))
        .execute()
    )
    drafts = response.get("drafts", [])[:limit]
    emails: list[dict[str, Any]] = []
    for draft in drafts:
        detail = (
            service.users()
            .drafts()
            .get(userId=USER_ID, id=draft["id"], format="metadata")
            .execute()
        )
        message = detail.get("message", {}) or {}
        emails.append(_parse_message(message))
    return emails


# Required parameters per action, validated *before* authentication so that a
# malformed request fails fast without triggering an OAuth/network round-trip.
# Handlers also re-check via ``_require`` so they remain safe if called directly.
_REQUIRED_PARAMS: dict[str, list[str]] = {
    "search_sender": ["sender"],
    "search_subject": ["subject"],
    "search_date_range": ["start_date", "end_date"],
    "search_gmail_query": ["query"],
    "get_email_by_id": ["message_id"],
    "count_emails": ["query"],
}


# Action registry: maps an action name to its handler. The handler signature is
# ``(service, parameters) -> list[dict] | int``.
_ACTIONS: dict[str, Callable[[Any, dict[str, Any]], Any]] = {
    "get_latest_emails": _action_get_latest_emails,
    "get_unread_emails": _action_get_unread_emails,
    "search_sender": _action_search_sender,
    "search_subject": _action_search_subject,
    "search_date_range": _action_search_date_range,
    "search_gmail_query": _action_search_gmail_query,
    "get_email_by_id": _action_get_email_by_id,
    "get_attachments": _action_get_attachments,
    "count_emails": _action_count_emails,
    "get_starred_emails": _action_get_starred_emails,
    "get_sent_emails": _action_get_sent_emails,
    "get_drafts": _action_get_drafts,
    "get_important_emails": _action_get_important_emails,
}


# --------------------------------------------------------------------------- #
# Response builders
# --------------------------------------------------------------------------- #
def _error(action: Optional[str], message: str) -> dict[str, Any]:
    """Build a structured error response."""
    return {"status": "error", "action": action, "message": message}


def _success(action: str, result: Any) -> dict[str, Any]:
    """Build a structured success response from a handler result."""
    if isinstance(result, int):  # count_emails
        return {"status": "success", "action": action, "count": result, "data": []}
    return {
        "status": "success",
        "action": action,
        "count": len(result),
        "data": result,
    }


# --------------------------------------------------------------------------- #
# Public interface
# --------------------------------------------------------------------------- #
def execute(request_json: dict) -> dict:
    """Single public entry point — route a JSON request to a Gmail operation.

    The function validates input, dispatches to the matching read-only handler,
    and always returns a JSON-compatible ``dict``. It never raises; every error
    is reported as ``{"status": "error", ...}``.

    Args:
        request_json: A request dict (a JSON string is also accepted and parsed)
            of the form ``{"action": <str>, "parameters": <dict>}``.

    Returns:
        On success::

            {"status": "success", "action": <str>, "count": <int>, "data": [...]}

        On failure::

            {"status": "error", "action": <str|None>, "message": <str>}
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

        # Validate required parameters before authenticating (router step 3).
        for required_key in _REQUIRED_PARAMS.get(action, []):
            _require(parameters, required_key)

        service = _get_service()
        result = handler(service, parameters)
        return _success(action, result)

    except GmailAgentError as exc:
        return _error(action, str(exc))
    except FileNotFoundError as exc:
        return _error(action, f"Authentication failed: {exc}")
    except (RefreshError, GoogleAuthError) as exc:
        return _error(action, f"Authentication failed: {exc}")
    except HttpError as exc:
        return _error(action, f"Gmail API error: {exc}")
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
        "gmail_agent - Gmail retrieval/search tool (JSON in, JSON out)\n\n"
        "Provide a JSON request one of these ways:\n\n"
        "  1) From a file (most reliable on Windows/PowerShell):\n"
        "       python gmail_agent.py request.json\n\n"
        "  2) Piped via stdin:\n"
        "       '{\"action\":\"get_unread_emails\",\"parameters\":{\"limit\":5}}'"
        " | python gmail_agent.py\n\n"
        "  3) As one argument with escaped quotes (PowerShell):\n"
        "       python gmail_agent.py '{\\\"action\\\":\\\"get_unread_emails\\\","
        "\\\"parameters\\\":{\\\"limit\\\":5}}'\n\n"
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
