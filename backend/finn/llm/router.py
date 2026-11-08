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

from finn.config import Settings, chain_for
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
        self.last_model: str | None = None
        self.settings = settings
        self.client = httpx.Client(
            transport=transport,
            timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) FINN/0.1"},
        )

    def complete_json(self, task: str, system: str, user: str, *, doc_hash: str = "") -> dict:
        chain = chain_for(task, self.settings)
        keys = [self._key(p, m, system, user, doc_hash) for p, m in chain]
        for (provider, model), key in zip(chain, keys, strict=True):
            cached = self._cached(key)
            if cached is not None:
                self._log(task, provider, model, True, 0, 0, 0)
                self.last_model = f"{provider}/{model}"
                return cached

        usable = [i for i, (p, _) in enumerate(chain) if getattr(self.settings, PROVIDERS[p][2])]
        failures: list[str] = []
        for i, (provider, model) in enumerate(chain):
            call, parse, key_attr, key_name = PROVIDERS[provider]
            api_key = getattr(self.settings, key_attr)
            if not api_key:
                failures.append(f"{provider}/{model}: missing {key_name}")
                continue
            retries = MAX_RETRIES if i == usable[-1] else 1
            try:
                start = time.monotonic()
                text, tin, tout = self._request(call, parse, api_key, model, system, user, retries)
                latency = int((time.monotonic() - start) * 1000)
                # Log before parsing: a 200 response spent quota even if the JSON is unusable.
                self._log(task, provider, model, False, tin, tout, latency)
                result = _parse_json(text)
            except LLMError as e:
                failures.append(f"{provider}/{model}: {e}")
                continue
            self.conn.execute(
                "INSERT OR REPLACE INTO llm_cache(key, response, created_at) VALUES (?,?,?)",
                (keys[i], json.dumps(result), datetime.now(IST).isoformat()),
            )
            self.conn.commit()
            self.last_model = f"{provider}/{model}"
            return result

        if not usable:
            raise LLMError(f"missing {PROVIDERS[chain[0][0]][3]}")
        raise LLMError("all models failed: " + "; ".join(failures))

    @staticmethod
    def _key(provider, model, system, user, doc_hash) -> str:
        return hashlib.sha256(f"{provider}|{model}|{system}|{user}|{doc_hash}".encode()).hexdigest()

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

    def _request(
        self, call, parse, api_key, model, system, user, retries: int = MAX_RETRIES
    ) -> tuple[str, int, int]:
        last = "no attempt"
        for attempt in range(retries + 1):
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
            if attempt == retries:
                break
            _sleep(_retry_delay(wait, attempt))
        raise LLMError(f"gave up after {retries} retries: {last}")

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
