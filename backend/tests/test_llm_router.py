import json
import logging

import httpx
import pytest
import respx

from finn.config import Settings
from finn.llm import LLMError, LLMRouter
from finn.llm import router as router_mod

GROQ = "https://api.groq.com/openai/v1/chat/completions"
GEMINI = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"
)


@pytest.fixture
def settings(tmp_path):
    return Settings(groq_api_key="g", gemini_api_key="m", data_dir=tmp_path, _env_file=None)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(router_mod, "_sleep", sleeps.append)
    return sleeps


def groq_ok(content='{"a": 1}'):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        },
    )


@respx.mock
def test_groq_json_roundtrip(conn, settings):
    route = respx.post(GROQ).mock(return_value=groq_ok())
    out = LLMRouter(conn, settings).complete_json("classify", "sys", "usr")
    assert out == {"a": 1}
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer g"
    body = json.loads(req.content)
    assert body["response_format"] == {"type": "json_object"} and body["temperature"] == 0


@respx.mock
def test_code_fences_stripped(conn, settings):
    respx.post(GROQ).mock(return_value=groq_ok('```json\n{"a": 2}\n```'))
    assert LLMRouter(conn, settings).complete_json("classify", "s", "u") == {"a": 2}


@respx.mock
def test_cache_hit_skips_http(conn, settings):
    route = respx.post(GROQ).mock(return_value=groq_ok())
    r = LLMRouter(conn, settings)
    r.complete_json("classify", "s", "u")
    assert r.complete_json("classify", "s", "u") == {"a": 1}
    assert route.call_count == 1
    st = r.stats()
    assert st["cached"] == 1 and st["calls"] == 2


@respx.mock
def test_429_then_ok(conn, settings, no_sleep):
    respx.post(GROQ).mock(
        side_effect=[httpx.Response(429, headers={"retry-after": "3"}), groq_ok()]
    )
    assert LLMRouter(conn, settings).complete_json("classify", "s", "u") == {"a": 1}
    assert no_sleep == [3.0]


@respx.mock
@pytest.mark.parametrize(
    ("retry_after", "slept"),
    [
        ("120", 60.0),  # capped
        ("-5", 0.0),  # floored
        ("inf", 1),  # non-finite -> backoff
        ("nan", 1),
        ("Wed, 21 Oct 2026 07:28:00 GMT", 1),  # HTTP-date form -> backoff
    ],
)
def test_retry_after_is_clamped_and_sanitised(conn, settings, no_sleep, retry_after, slept):
    respx.post(GROQ).mock(
        side_effect=[httpx.Response(429, headers={"retry-after": retry_after}), groq_ok()]
    )
    assert LLMRouter(conn, settings).complete_json("classify", "s", "u") == {"a": 1}
    assert no_sleep == [slept]


@respx.mock
def test_corrupt_cache_row_is_a_miss(conn, settings):
    route = respx.post(GROQ).mock(return_value=groq_ok())
    r = LLMRouter(conn, settings)
    r.complete_json("classify", "s", "u")
    conn.execute("UPDATE llm_cache SET response = '{not json'")
    assert r.complete_json("classify", "s", "u") == {"a": 1}
    assert route.call_count == 2
    (fixed,) = conn.execute("SELECT response FROM llm_cache").fetchone()
    assert json.loads(fixed) == {"a": 1}
    assert r.stats()["cached"] == 0


@respx.mock
def test_persistent_5xx_raises_after_backoff(conn, settings, no_sleep):
    respx.post(GROQ).mock(return_value=httpx.Response(503))
    with pytest.raises(LLMError):
        LLMRouter(conn, settings).complete_json("classify", "s", "u")
    assert no_sleep == [1, 2, 4]


@respx.mock
def test_invalid_json_raises_llmerror(conn, settings):
    respx.post(GROQ).mock(return_value=groq_ok("not json"))
    with pytest.raises(LLMError):
        LLMRouter(conn, settings).complete_json("classify", "s", "u")


@respx.mock
def test_usage_logged_gemini(conn, settings):
    route = respx.post(GEMINI).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
                "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 500},
            },
        )
    )
    r = LLMRouter(conn, settings)
    assert r.complete_json("extract_transcript", "sys", "usr") == {"ok": True}
    req = route.calls[0].request
    assert req.headers["x-goog-api-key"] == "m"
    assert json.loads(req.content)["systemInstruction"]["parts"][0]["text"] == "sys"
    st = r.stats()
    assert st["input_tokens"] == 1000 and st["output_tokens"] == 500
    assert st["usd_list_price"] == pytest.approx(0.0003 + 0.00125)


def test_usage_logged_groq(conn, settings):
    with respx.mock:
        respx.post(GROQ).mock(return_value=groq_ok())
        r = LLMRouter(conn, settings)
        r.complete_json("oneliner", "s", "u")
    st = r.stats()
    assert (st["input_tokens"], st["output_tokens"]) == (11, 7)


def test_missing_key_raises_before_http(conn, tmp_path):
    s = Settings(groq_api_key="", data_dir=tmp_path, _env_file=None)
    with respx.mock, pytest.raises(LLMError, match="missing GROQ_API_KEY"):
        LLMRouter(conn, s).complete_json("classify", "s", "u")


def test_unknown_model_costs_zero_and_warns(caplog):
    from finn.llm.costs import list_price_usd

    with caplog.at_level(logging.WARNING, logger="finn.llm.costs"):
        assert list_price_usd("unpriced-model-x", 100, 100) == 0.0
    assert "unpriced-model-x" in caplog.text


def test_known_model_does_not_warn(caplog):
    from finn.llm.costs import list_price_usd

    with caplog.at_level(logging.WARNING, logger="finn.llm.costs"):
        assert list_price_usd("llama-3.1-8b-instant", 1_000_000, 0) == 0.05
    assert caplog.text == ""


def gemini_resp(body):
    return httpx.Response(200, json=body)


@respx.mock
@pytest.mark.parametrize(
    ("body", "needle"),
    [
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "SAFETY"),
        ({"candidates": [{"finishReason": "SAFETY"}]}, "SAFETY"),
    ],
)
def test_gemini_safety_block_raises_clear_error(conn, settings, no_sleep, body, needle):
    route = respx.post(GEMINI).mock(return_value=gemini_resp(body))
    with pytest.raises(LLMError, match=needle):
        LLMRouter(conn, settings).complete_json("extract_transcript", "s", "u")
    assert route.call_count == 1 and no_sleep == []


@respx.mock
def test_invalid_json_still_logs_usage(conn, settings):
    respx.post(GROQ).mock(return_value=groq_ok("not json"))
    r = LLMRouter(conn, settings)
    with pytest.raises(LLMError):
        r.complete_json("classify", "s", "u")
    row = conn.execute("SELECT cached, input_tokens, output_tokens FROM llm_calls").fetchone()
    assert tuple(row) == (0, 11, 7)
    assert conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0] == 0


@respx.mock
def test_gemini_thinking_tokens_count_as_output(conn, settings):
    respx.post(GEMINI).mock(
        return_value=gemini_resp(
            {
                "candidates": [{"content": {"parts": [{"text": "{}"}]}}],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 5,
                    "thoughtsTokenCount": 20,
                },
            }
        )
    )
    r = LLMRouter(conn, settings)
    r.complete_json("extract_transcript", "s", "u")
    assert r.stats()["output_tokens"] == 25
