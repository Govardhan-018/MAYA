"""weather_agent.py — Weather retrieval plugin using Open-Meteo (TOOL ONLY).

This module is a *pure tool*. It performs **no** analysis, reasoning,
recommendations, summarization, or decision making, and makes no predictions
beyond the data Open-Meteo returns. It only:

    1. Receives a JSON-compatible ``dict`` request.
    2. Calls the Open-Meteo Geocoding and Forecast APIs.
    3. Retrieves the requested weather information.
    4. Returns a JSON-compatible ``dict`` response.

All intelligence belongs to the calling "Brain Agent". The single public
entry point is :func:`execute`.

APIs (no key required):
    * Geocoding: https://geocoding-api.open-meteo.com/v1/search
    * Forecast:  https://api.open-meteo.com/v1/forecast

Dependencies (install once)::

    pip install requests python-dotenv

Optional environment overrides (read from ``.env`` via python-dotenv):
    * ``OPEN_METEO_TIMEOUT``  - per-request timeout in seconds (default 15)
    * ``OPEN_METEO_RETRIES``  - retry attempts on network/5xx errors (default 3)
    * ``OPEN_METEO_BACKOFF``  - base backoff seconds between retries (default 0.5)

CLI usage::

    python weather_agent.py request.json
    python weather_agent.py '{"action": "current_weather", "parameters": {"location": "Bangalore"}}'
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from typing import Any, Callable, Optional

import requests
from dotenv import load_dotenv

__all__ = ["execute", "PLUGIN_INFO"]


# --------------------------------------------------------------------------- #
# Plugin metadata
# --------------------------------------------------------------------------- #
PLUGIN_INFO: dict[str, str] = {
    "name": "weather_agent",
    "agent_name": "WeatherAgent",
    "version": "1.0.0",
    "type": "tool",
    "input_format": "json",
    "output_format": "json",
    "entrypoint": "execute",
    "description": "Weather retrieval plugin using Open-Meteo",
}


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
_BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))

# No API key is needed, but load .env anyway to honor optional overrides.
load_dotenv()
load_dotenv(os.path.join(_BASE_DIR, ".env"), override=False)


def _env_number(name: str, default: float, cast: Callable[[str], float]) -> float:
    """Read a numeric environment override, falling back on bad/missing values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return default


GEOCODING_URL: str = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL: str = "https://api.open-meteo.com/v1/forecast"

REQUEST_TIMEOUT: float = _env_number("OPEN_METEO_TIMEOUT", 15.0, float)
MAX_RETRIES: int = int(_env_number("OPEN_METEO_RETRIES", 3, int))
RETRY_BACKOFF: float = _env_number("OPEN_METEO_BACKOFF", 0.5, float)

GEOCODE_RESULTS: int = 10  # max matches returned by search_location
MAX_FORECAST_DAYS: int = 16  # Open-Meteo hard cap
DEFAULT_FORECAST_DAYS: int = 7
DEFAULT_HOURS: int = 24
DEFAULT_NEXT_DAYS: int = 5

CURRENT_FIELDS: list[str] = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "is_day",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
]
HOURLY_FIELDS: list[str] = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation_probability",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
]
DAILY_FIELDS: list[str] = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
]

# WMO weather interpretation codes -> human-readable text (a fixed standard
# lookup table, not analysis). Source: Open-Meteo / WMO code table 4677.
_WMO_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class WeatherAgentError(Exception):
    """Raised for any handled error whose message is safe to return.

    Covers parameter validation, location-not-found, network failures, and
    Open-Meteo error responses. These map to a structured ``status: error``
    response instead of crashing the tool.
    """


# --------------------------------------------------------------------------- #
# HTTP layer (with retry/backoff)
# --------------------------------------------------------------------------- #
_SESSION: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Return a cached :class:`requests.Session` (Open-Meteo needs no auth)."""
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET ``url`` with retry/backoff and return the parsed JSON payload.

    Retries on network errors and HTTP 5xx responses (transient); 4xx errors
    are surfaced immediately using Open-Meteo's ``reason`` field when present.

    Raises:
        WeatherAgentError: On exhausted retries, a 4xx/5xx error, or bad JSON.
    """
    clean_params = {key: value for key, value in params.items() if value is not None}
    session = _get_session()
    last_error: str = "unknown error"

    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, params=clean_params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_error = f"network error ({exc})"
        else:
            if response.status_code >= 500:
                last_error = f"server error (HTTP {response.status_code})"
            elif response.status_code != 200:
                # Client error — do not retry; surface the API's reason.
                reason = None
                try:
                    reason = response.json().get("reason")
                except ValueError:
                    reason = None
                raise WeatherAgentError(
                    reason or f"Open-Meteo request failed (HTTP {response.status_code})"
                )
            else:
                try:
                    return response.json()
                except ValueError:
                    raise WeatherAgentError("Open-Meteo returned a non-JSON response")

        # Backoff before the next attempt (skip after the final attempt).
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF * (2 ** attempt))

    raise WeatherAgentError(
        f"Open-Meteo request failed after {MAX_RETRIES} attempts: {last_error}"
    )


# --------------------------------------------------------------------------- #
# Parameter helpers
# --------------------------------------------------------------------------- #
def _require(parameters: dict[str, Any], key: str) -> Any:
    """Return ``parameters[key]`` or raise if missing/blank."""
    value = parameters.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise WeatherAgentError(f"Missing {key} parameter")
    return value


def _require_list(parameters: dict[str, Any], key: str) -> list[str]:
    """Return a validated non-empty list of non-blank strings."""
    value = parameters.get(key)
    if value is None:
        raise WeatherAgentError(f"Missing {key} parameter")
    if not isinstance(value, list) or not value:
        raise WeatherAgentError(f"Parameter '{key}' must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise WeatherAgentError(f"Parameter '{key}' must contain non-empty strings")
    return value


def _get_int(
    parameters: dict[str, Any],
    key: str,
    default: int,
    minimum: int = 1,
    maximum: Optional[int] = None,
) -> int:
    """Parse and clamp an integer parameter."""
    raw = parameters.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise WeatherAgentError(f"Parameter '{key}' must be an integer")
    if value < minimum:
        raise WeatherAgentError(f"Parameter '{key}' must be >= {minimum}")
    if maximum is not None:
        value = min(value, maximum)
    return value


def _get_coord(parameters: dict[str, Any], key: str, low: float, high: float) -> float:
    """Parse and range-check a latitude/longitude parameter."""
    value = parameters.get(key)
    if value is None:
        raise WeatherAgentError(f"Missing {key} parameter")
    try:
        coord = float(value)
    except (TypeError, ValueError):
        raise WeatherAgentError(f"Parameter '{key}' must be a number")
    if not low <= coord <= high:
        raise WeatherAgentError(f"Parameter '{key}' must be between {low} and {high}")
    return coord


# --------------------------------------------------------------------------- #
# Data shaping (pure mapping — no interpretation)
# --------------------------------------------------------------------------- #
def _describe(code: Any) -> str:
    """Map a WMO weather code to its standard description (``""`` if unknown)."""
    if code is None:
        return ""
    try:
        return _WMO_CODES.get(int(code), "Unknown")
    except (TypeError, ValueError):
        return "Unknown"


def _safe_index(sequence: Any, index: int) -> Any:
    """Return ``sequence[index]`` if valid, else ``None``."""
    if isinstance(sequence, list) and 0 <= index < len(sequence):
        return sequence[index]
    return None


def _map_location(result: dict[str, Any]) -> dict[str, Any]:
    """Map a raw geocoding result to a stable metadata dict."""
    return {
        "id": result.get("id"),
        "name": result.get("name", ""),
        "latitude": result.get("latitude"),
        "longitude": result.get("longitude"),
        "country": result.get("country", ""),
        "country_code": result.get("country_code", ""),
        "admin1": result.get("admin1", ""),
        "timezone": result.get("timezone", ""),
        "population": result.get("population"),
        "elevation": result.get("elevation"),
        "feature_code": result.get("feature_code", ""),
    }


def _build_current(
    name: str, latitude: float, longitude: float, forecast: dict[str, Any]
) -> dict[str, Any]:
    """Build the standard current-weather dict from a forecast payload."""
    current = forecast.get("current", {}) or {}
    code = current.get("weather_code")
    return {
        "location": name,
        "latitude": latitude,
        "longitude": longitude,
        "temperature": current.get("temperature_2m"),
        "feels_like": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "wind_speed": current.get("wind_speed_10m"),
        "wind_direction": current.get("wind_direction_10m"),
        "weather_code": code,
        "weather_description": _describe(code),
        "is_day": bool(current.get("is_day")),
        "time": current.get("time", ""),
    }


def _build_daily(forecast: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a list of standard daily-forecast dicts from a forecast payload."""
    daily = forecast.get("daily", {}) or {}
    dates = daily.get("time", []) or []
    out: list[dict[str, Any]] = []
    for i, date in enumerate(dates):
        code = _safe_index(daily.get("weather_code"), i)
        out.append(
            {
                "date": date,
                "temp_max": _safe_index(daily.get("temperature_2m_max"), i),
                "temp_min": _safe_index(daily.get("temperature_2m_min"), i),
                "precipitation_probability": _safe_index(
                    daily.get("precipitation_probability_max"), i
                ),
                "weather_code": code,
                "weather_description": _describe(code),
            }
        )
    return out


def _build_hourly(forecast: dict[str, Any], hours: int) -> list[dict[str, Any]]:
    """Build a list of hourly dicts (up to ``hours``) from a forecast payload."""
    hourly = forecast.get("hourly", {}) or {}
    times = hourly.get("time", []) or []
    out: list[dict[str, Any]] = []
    for i, timestamp in enumerate(times[:hours]):
        code = _safe_index(hourly.get("weather_code"), i)
        out.append(
            {
                "time": timestamp,
                "temperature": _safe_index(hourly.get("temperature_2m"), i),
                "feels_like": _safe_index(hourly.get("apparent_temperature"), i),
                "humidity": _safe_index(hourly.get("relative_humidity_2m"), i),
                "precipitation_probability": _safe_index(
                    hourly.get("precipitation_probability"), i
                ),
                "weather_code": code,
                "weather_description": _describe(code),
                "wind_speed": _safe_index(hourly.get("wind_speed_10m"), i),
                "wind_direction": _safe_index(hourly.get("wind_direction_10m"), i),
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Open-Meteo fetch helpers
# --------------------------------------------------------------------------- #
def _resolve_location(location: str) -> dict[str, Any]:
    """Geocode a location name and return the top match.

    Raises:
        WeatherAgentError: No matching location was found.
    """
    results = _geocode(location)
    return results[0]


def _geocode(location: str) -> list[dict[str, Any]]:
    """Return geocoding matches for ``location`` (newest API order preserved).

    Raises:
        WeatherAgentError: No matching location was found.
    """
    payload = _get_json(
        GEOCODING_URL,
        {"name": location, "count": GEOCODE_RESULTS, "language": "en", "format": "json"},
    )
    results = payload.get("results") or []
    if not results:
        raise WeatherAgentError(f"Location not found: {location}")
    return results


def _fetch_forecast(
    latitude: float,
    longitude: float,
    current: bool = False,
    hourly: bool = False,
    daily: bool = False,
    forecast_days: Optional[int] = None,
) -> dict[str, Any]:
    """Fetch a forecast payload for the requested sections."""
    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "auto",
    }
    if current:
        params["current"] = ",".join(CURRENT_FIELDS)
    if hourly:
        params["hourly"] = ",".join(HOURLY_FIELDS)
    if daily:
        params["daily"] = ",".join(DAILY_FIELDS)
    if forecast_days is not None:
        params["forecast_days"] = max(1, min(forecast_days, MAX_FORECAST_DAYS))
    return _get_json(FORECAST_URL, params)


# --------------------------------------------------------------------------- #
# Core data builders (resolve -> fetch -> shape). Reused by handlers and bulk.
# Each raises WeatherAgentError on failure.
# --------------------------------------------------------------------------- #
def _current_data(location: str) -> dict[str, Any]:
    """Current weather for a named location."""
    loc = _resolve_location(location)
    forecast = _fetch_forecast(loc["latitude"], loc["longitude"], current=True)
    return _build_current(loc["name"], loc["latitude"], loc["longitude"], forecast)


def _daily_data(location: str, days: int) -> dict[str, Any]:
    """Daily forecast for a named location."""
    loc = _resolve_location(location)
    forecast = _fetch_forecast(
        loc["latitude"], loc["longitude"], daily=True, forecast_days=days
    )
    daily = _build_daily(forecast)
    return {
        "location": loc["name"],
        "latitude": loc["latitude"],
        "longitude": loc["longitude"],
        "count": len(daily),
        "daily": daily,
    }


def _hourly_data(location: str, hours: int) -> dict[str, Any]:
    """Hourly forecast (up to ``hours``) for a named location."""
    loc = _resolve_location(location)
    days_needed = min(MAX_FORECAST_DAYS, max(1, math.ceil(hours / 24)))
    forecast = _fetch_forecast(
        loc["latitude"], loc["longitude"], hourly=True, forecast_days=days_needed
    )
    hourly = _build_hourly(forecast, hours)
    return {
        "location": loc["name"],
        "latitude": loc["latitude"],
        "longitude": loc["longitude"],
        "count": len(hourly),
        "hourly": hourly,
    }


def _today_data(location: str) -> dict[str, Any]:
    """Current conditions plus today's daily forecast for a named location."""
    loc = _resolve_location(location)
    forecast = _fetch_forecast(
        loc["latitude"], loc["longitude"], current=True, daily=True, forecast_days=1
    )
    daily = _build_daily(forecast)
    return {
        "location": loc["name"],
        "latitude": loc["latitude"],
        "longitude": loc["longitude"],
        "current": _build_current(
            loc["name"], loc["latitude"], loc["longitude"], forecast
        ),
        "today": daily[0] if daily else None,
    }


def _tomorrow_data(location: str) -> dict[str, Any]:
    """Tomorrow's daily forecast for a named location."""
    loc = _resolve_location(location)
    forecast = _fetch_forecast(
        loc["latitude"], loc["longitude"], daily=True, forecast_days=2
    )
    daily = _build_daily(forecast)
    return {
        "location": loc["name"],
        "latitude": loc["latitude"],
        "longitude": loc["longitude"],
        "tomorrow": daily[1] if len(daily) > 1 else None,
    }


def _next_days_data(location: str, days: int) -> dict[str, Any]:
    """The next ``days`` days (starting tomorrow) for a named location."""
    loc = _resolve_location(location)
    forecast = _fetch_forecast(
        loc["latitude"], loc["longitude"], daily=True, forecast_days=days + 1
    )
    daily = _build_daily(forecast)
    upcoming = daily[1 : days + 1]
    return {
        "location": loc["name"],
        "latitude": loc["latitude"],
        "longitude": loc["longitude"],
        "count": len(upcoming),
        "days": upcoming,
    }


def _multi_current(locations: list[str]) -> dict[str, Any]:
    """Current weather for each location; per-location errors are inlined."""
    results: dict[str, Any] = {}
    for location in locations:
        try:
            results[location] = _current_data(location)
        except WeatherAgentError as exc:
            results[location] = {"error": str(exc)}
    return results


# --------------------------------------------------------------------------- #
# Action handlers — each returns a response fragment merged into the base
# success envelope. None interpret, rank, recommend, or summarize.
# --------------------------------------------------------------------------- #
def _action_current_weather(parameters: dict[str, Any]) -> dict[str, Any]:
    """Current weather for a single location."""
    return {"data": _current_data(_require(parameters, "location"))}


def _action_weather_today(parameters: dict[str, Any]) -> dict[str, Any]:
    """Current conditions plus today's daily forecast."""
    return {"data": _today_data(_require(parameters, "location"))}


def _action_hourly_forecast(parameters: dict[str, Any]) -> dict[str, Any]:
    """Hourly forecast for the next ``hours`` hours."""
    location = _require(parameters, "location")
    hours = _get_int(parameters, "hours", DEFAULT_HOURS, maximum=MAX_FORECAST_DAYS * 24)
    return {"data": _hourly_data(location, hours)}


def _action_daily_forecast(parameters: dict[str, Any]) -> dict[str, Any]:
    """Daily forecast for the next ``days`` days."""
    location = _require(parameters, "location")
    days = _get_int(parameters, "days", DEFAULT_FORECAST_DAYS, maximum=MAX_FORECAST_DAYS)
    return {"data": _daily_data(location, days)}


def _action_weather_tomorrow(parameters: dict[str, Any]) -> dict[str, Any]:
    """Tomorrow's daily forecast."""
    return {"data": _tomorrow_data(_require(parameters, "location"))}


def _action_weather_next_days(parameters: dict[str, Any]) -> dict[str, Any]:
    """The next ``days`` days (starting tomorrow)."""
    location = _require(parameters, "location")
    days = _get_int(
        parameters, "days", DEFAULT_NEXT_DAYS, maximum=MAX_FORECAST_DAYS - 1
    )
    return {"data": _next_days_data(location, days)}


def _action_weather_multiple_locations(parameters: dict[str, Any]) -> dict[str, Any]:
    """Current weather for multiple locations, grouped by location."""
    locations = _require_list(parameters, "locations")
    return {"results": _multi_current(locations)}


def _action_compare_locations(parameters: dict[str, Any]) -> dict[str, Any]:
    """Current weather for multiple locations side by side (no ranking)."""
    locations = _require_list(parameters, "locations")
    return {"results": _multi_current(locations)}


def _action_search_location(parameters: dict[str, Any]) -> dict[str, Any]:
    """Geocode a location name to coordinates and metadata."""
    location = _require(parameters, "location")
    results = _geocode(location)
    mapped = [_map_location(item) for item in results]
    return {"data": {"query": location, "count": len(mapped), "results": mapped}}


def _action_weather_by_coordinates(parameters: dict[str, Any]) -> dict[str, Any]:
    """Current weather for explicit latitude/longitude coordinates."""
    latitude = _get_coord(parameters, "latitude", -90.0, 90.0)
    longitude = _get_coord(parameters, "longitude", -180.0, 180.0)
    forecast = _fetch_forecast(latitude, longitude, current=True)
    name = f"{latitude},{longitude}"
    return {"data": _build_current(name, latitude, longitude, forecast)}


def _dispatch_bulk(item: dict[str, Any]) -> dict[str, Any]:
    """Execute one sub-request inside ``weather_bulk_request``."""
    request_type = str(item.get("type") or "current").lower()
    location = _require(item, "location")

    if request_type == "current":
        return _current_data(location)
    if request_type in ("forecast", "daily"):
        days = _get_int(item, "days", DEFAULT_FORECAST_DAYS, maximum=MAX_FORECAST_DAYS)
        return _daily_data(location, days)
    if request_type == "hourly":
        hours = _get_int(item, "hours", DEFAULT_HOURS, maximum=MAX_FORECAST_DAYS * 24)
        return _hourly_data(location, hours)
    if request_type == "today":
        return _today_data(location)
    if request_type == "tomorrow":
        return _tomorrow_data(location)
    raise WeatherAgentError(f"Unsupported bulk request type: {request_type}")


def _action_weather_bulk_request(parameters: dict[str, Any]) -> dict[str, Any]:
    """Run several weather sub-requests in a single call."""
    requests_list = parameters.get("requests")
    if not isinstance(requests_list, list) or not requests_list:
        raise WeatherAgentError("Parameter 'requests' must be a non-empty list")

    results: list[dict[str, Any]] = []
    for index, item in enumerate(requests_list):
        if not isinstance(item, dict):
            results.append(
                {"status": "error", "message": f"Request #{index} must be an object"}
            )
            continue
        entry: dict[str, Any] = {
            "location": item.get("location"),
            "type": str(item.get("type") or "current").lower(),
        }
        try:
            entry["status"] = "success"
            entry["data"] = _dispatch_bulk(item)
        except WeatherAgentError as exc:
            entry["status"] = "error"
            entry["message"] = str(exc)
        results.append(entry)
    return {"results": results}


# Required parameters per action, validated before any network call. Handlers
# re-validate (and do deeper checks) so they remain safe if called directly.
_REQUIRED_PARAMS: dict[str, list[str]] = {
    "current_weather": ["location"],
    "weather_today": ["location"],
    "hourly_forecast": ["location"],
    "daily_forecast": ["location"],
    "weather_tomorrow": ["location"],
    "weather_next_days": ["location"],
    "weather_multiple_locations": ["locations"],
    "compare_locations": ["locations"],
    "search_location": ["location"],
    "weather_by_coordinates": ["latitude", "longitude"],
    "weather_bulk_request": ["requests"],
}


# Action registry: maps an action name to its handler.
_ACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "current_weather": _action_current_weather,
    "weather_today": _action_weather_today,
    "hourly_forecast": _action_hourly_forecast,
    "daily_forecast": _action_daily_forecast,
    "weather_tomorrow": _action_weather_tomorrow,
    "weather_next_days": _action_weather_next_days,
    "weather_multiple_locations": _action_weather_multiple_locations,
    "compare_locations": _action_compare_locations,
    "search_location": _action_search_location,
    "weather_by_coordinates": _action_weather_by_coordinates,
    "weather_bulk_request": _action_weather_bulk_request,
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
    """Single public entry point — route a JSON request to an Open-Meteo call.

    Validates input, dispatches to the matching handler, and always returns a
    JSON-compatible ``dict``. It never raises; every error becomes a
    ``{"status": "error", ...}`` response.

    Args:
        request_json: A request dict (a JSON string is also accepted and parsed)
            of the form ``{"action": <str>, "parameters": <dict>}``.

    Returns:
        On success a ``{"status": "success", "action": <str>, ...}`` envelope
        whose remaining keys depend on the action (``data`` or ``results``).
        On failure, ``{"status": "error", "action": <str|None>, "message": ...}``.
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

    except WeatherAgentError as exc:
        return _error(action, str(exc))
    except Exception as exc:  # noqa: BLE001 - tool must never crash the Brain.
        return _error(action, f"Unexpected error: {exc}")


# --------------------------------------------------------------------------- #
# CLI shim — accept a JSON request from a file, an argument, or stdin.
# --------------------------------------------------------------------------- #
def _read_stdin() -> str:
    """Read stdin as bytes and decode with ``utf-8-sig`` to strip any BOM."""
    return sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")


def _print_usage() -> None:
    """Print CLI usage to stderr (shown when run on a TTY with no input)."""
    sys.stderr.write(
        "weather_agent - Weather retrieval tool using Open-Meteo (JSON in/out)\n\n"
        "Provide a JSON request one of these ways:\n\n"
        "  1) From a file (most reliable on Windows/PowerShell):\n"
        "       python weather_agent.py request.json\n\n"
        "  2) Piped via stdin:\n"
        "       '{\"action\":\"current_weather\",\"parameters\":{\"location\":\"Bangalore\"}}'"
        " | python weather_agent.py\n\n"
        "  3) As one argument with escaped quotes (PowerShell):\n"
        "       python weather_agent.py '{\\\"action\\\":\\\"current_weather\\\","
        "\\\"parameters\\\":{\\\"location\\\":\\\"Bangalore\\\"}}'\n\n"
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
