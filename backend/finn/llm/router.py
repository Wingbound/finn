"""Task-routed LLM client with response cache, retries and a cost log."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from datetime import datetime

import httpx

from finn.config import Settings, route_for
from finn.llm.costs import list_price_usd
from finn.llm.providers import PROVIDERS, TIMEOUT, LLMError
from finn.models import IST

MAX_RETRIES = 3
BACKOFF_S = (1, 2, 4)
MAX_RETRY_AFTER_S = 60.0
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _sleep(seconds: float) -> None:  # patched in tests
    time.sleep(seconds)


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    """The server's retry-after clamped to [0, 60] s; backoff if absent or not a finite number."""
    if retry_after is None:
        return BACKOFF_S[attempt]
    try:
        delay = float(retry_after)
    except ValueError:  # e.g. the HTTP-date form
        return BACKOFF_S[attempt]
    if not math.isfinite(delay):
        return BACKOFF_S[attempt]
    return min(max(delay, 0.0), MAX_RETRY_AFTER_S)


def _parse_json(text: str) -> dict:
    m = _FENCE.match(text)
    if m:
        text = m.group(1)
    try:
        out = json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"invalid JSON from model: {e}") from e
    if not isinstance(out, dict):
        raise LLMError("model returned JSON that is not an object")
    return out


class LLMRouter:
    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ):
        self.conn = conn
        self.settings = settings
        self.client = httpx.Client(
            transport=transport,
            timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) FINN/0.1"},
        )

    def complete_json(self, task: str, system: str, user: str, *, doc_hash: str = "") -> dict:
        provider, model = route_for(task, self.settings)
        key = hashlib.sha256(f"{provider}|{model}|{system}|{user}|{doc_hash}".encode()).hexdigest()
        cached = self._cached(key)
        if cached is not None:
            self._log(task, provider, model, True, 0, 0, 0)
            return cached

        call, parse, key_attr, key_name = PROVIDERS[provider]
        api_key = getattr(self.settings, key_attr)
        if not api_key:
            raise LLMError(f"missing {key_name}")

        start = time.monotonic()
        text, tin, tout = self._request(call, parse, api_key, model, system, user)
        latency = int((time.monotonic() - start) * 1000)
        # Log before parsing: a 200 response spent quota even if the JSON is unusable.
        # (Calls that never got a 200 after retries are not logged.)
        self._log(task, provider, model, False, tin, tout, latency)
        result = _parse_json(text)
        self.conn.execute(
            "INSERT OR REPLACE INTO llm_cache(key, response, created_at) VALUES (?,?,?)",
            (key, json.dumps(result), datetime.now(IST).isoformat()),
        )
        self.conn.commit()
        return result

    def _cached(self, key: str) -> dict | None:
        """The cached reply, or None on a miss. A corrupt row counts as a miss and is
        overwritten by the fresh reply."""
        row = self.conn.execute("SELECT response FROM llm_cache WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        try:
            out = json.loads(row[0])
        except json.JSONDecodeError:
            return None
        return out if isinstance(out, dict) else None

    def _request(self, call, parse, api_key, model, system, user) -> tuple[str, int, int]:
        last = "no attempt"
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = call(self.client, api_key, model, system, user)
            except httpx.TransportError as e:
                last, wait = f"transport error: {e}", None
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last, wait = f"HTTP {resp.status_code}", resp.headers.get("retry-after")
                elif resp.status_code >= 400:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                else:
                    try:
                        return parse(resp.json())
                    except (ValueError, KeyError, IndexError, TypeError) as e:
                        raise LLMError(f"unexpected response shape: {e!r}") from e
            if attempt == MAX_RETRIES:
                break
            _sleep(_retry_delay(wait, attempt))
        raise LLMError(f"gave up after {MAX_RETRIES} retries: {last}")

    def _log(self, task, provider, model, cached, tin, tout, latency) -> None:
        self.conn.execute(
            "INSERT INTO llm_calls(ts, task, provider, model, cached, input_tokens, output_tokens,"
            " latency_ms, usd_list_price) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                datetime.now(IST).isoformat(),
                task,
                provider,
                model,
                int(cached),
                tin,
                tout,
                latency,
                list_price_usd(model, tin, tout),
            ),
        )
        self.conn.commit()

    def stats(self) -> dict:
        r = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(cached),0), COALESCE(SUM(input_tokens),0),"
            " COALESCE(SUM(output_tokens),0), COALESCE(SUM(usd_list_price),0.0) FROM llm_calls"
        ).fetchone()
        return {
            "calls": r[0],
            "cached": r[1],
            "input_tokens": r[2],
            "output_tokens": r[3],
            "usd_list_price": r[4],
        }
