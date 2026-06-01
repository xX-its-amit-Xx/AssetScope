"""Shared HTTP helpers for the external-API tools.

A single pooled ``httpx.Client`` with sensible timeouts, a descriptive
User-Agent (good API citizenship), and bounded retries.

Failure handling is deliberate:

* **429 / 503** (rate limit / temporarily unavailable) are *transient* — retried
  with exponential backoff on the httpx path. They are NOT sent to curl, since
  curl would just hit the same rate limit.
* **403 / 406 / 451** indicate a bot/WAF block. ClinicalTrials.gov (behind
  Akamai) rejects Python's TLS fingerprint with 403 even with browser-identical
  headers, while the system ``curl`` binary passes. So for these we transparently
  fall back to ``curl`` (preinstalled on Windows; installed in the API image).
  ``curl --fail`` is used so an error page is never silently parsed as JSON.
"""

from __future__ import annotations

import json as _json
import logging
import shutil
import subprocess

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from assetscope.config import get_settings

logger = logging.getLogger("assetscope.tools.http")

_client: httpx.Client | None = None
_CURL = shutil.which("curl")

# WAF/TLS-fingerprint blocks → try curl (different fingerprint).
_BLOCK_STATUS = {403, 406, 451}
# Genuinely transient → retry with backoff on the httpx path.
_RETRY_STATUS = {429, 503}


def _user_agent() -> str:
    return f"AssetScope/0.1 (biopharma CI; mailto:{get_settings().contact_email})"


def get_client() -> httpx.Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = httpx.Client(
            timeout=settings.http_timeout,
            follow_redirects=True,
            headers={"User-Agent": _user_agent(), "Accept": "application/json"},
        )
    return _client


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRY_STATUS
    return False


# Retry transport failures + 429/503 with backoff. WAF blocks (403/406/451)
# raise immediately so the caller can fall back to curl.
@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=0.8, min=0.8, max=10),
    retry=retry_if_exception(_is_retryable),
)
def _httpx_request(method: str, url: str, *, params=None, json_body=None, client=None) -> httpx.Response:
    cli = client or get_client()
    resp = cli.request(method, url, params=params, json=json_body)
    resp.raise_for_status()
    return resp


def _curl_fetch(
    url: str, *, params=None, json_body=None, method: str = "GET", accept: str = "application/json"
) -> str | None:
    """Fetch via the system curl binary (different TLS fingerprint). Returns the
    response body text, or ``None`` if curl is unavailable. Uses ``--fail`` so an
    HTTP error page is reported as a failure rather than returned as a body."""
    if not _CURL:
        return None
    settings = get_settings()
    full = str(httpx.URL(url, params=params)) if params else url
    timeout = int(settings.http_timeout)
    cmd = [
        _CURL, "-sS", "--fail", "-L", "--compressed", "--max-time", str(timeout),
        "-A", _user_agent(), "-H", f"Accept: {accept}",
    ]
    if method == "POST":
        cmd += ["-X", "POST", "-H", "Content-Type: application/json",
                "--data-binary", _json.dumps(json_body or {})]
    cmd.append(full)
    # Decode as UTF-8 explicitly: the API bodies are UTF-8, but Windows defaults
    # subprocess text decoding to the locale codec (cp1252), which corrupts/raises
    # on non-ASCII bytes (e.g. an en-dash in a trial title).
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout + 15,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"curl failed (rc={proc.returncode}): {(proc.stderr or '')[:200]}")
    return proc.stdout


def _decode(body: str, want: str, original: BaseException):
    if want != "json":
        return body
    try:
        return _json.loads(body)
    except _json.JSONDecodeError:
        # The fallback returned something that isn't JSON (e.g. an error page);
        # surface the original failure rather than a confusing decode error.
        raise original from None


def _with_fallback(method: str, url: str, *, params=None, json_body=None, client=None, want="json"):
    accept = "application/json"
    try:
        resp = _httpx_request(method, url, params=params, json_body=json_body, client=client)
        return resp.json() if want == "json" else resp.text
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in _BLOCK_STATUS and _CURL:
            logger.info("httpx %s blocked for %s; falling back to curl.",
                        exc.response.status_code, url)
            body = _curl_fetch(url, params=params, json_body=json_body, method=method, accept=accept)
            if body is not None:
                return _decode(body, want, exc)
        raise
    except httpx.TransportError as exc:
        if _CURL:
            body = _curl_fetch(url, params=params, json_body=json_body, method=method, accept=accept)
            if body is not None:
                return _decode(body, want, exc)
        raise


def get_json(url: str, params: dict | None = None, client: httpx.Client | None = None) -> dict:
    return _with_fallback("GET", url, params=params, client=client, want="json")


def get_text(url: str, params: dict | None = None, client: httpx.Client | None = None) -> str:
    return _with_fallback("GET", url, params=params, client=client, want="text")


def post_json(
    url: str, json_body: dict, params: dict | None = None, client: httpx.Client | None = None
) -> dict:
    return _with_fallback("POST", url, params=params, json_body=json_body, client=client, want="json")
