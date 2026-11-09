import json
import logging

import httpx
import pytest
import respx

from finn.config import Settings, chain_for
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
        ("60", 60.0),  # at the cap is still pacing (above it is quota)
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
def test_persistent_5xx_raises_after_backoff(conn, tmp_path, no_sleep):
    s = Settings(groq_api_key="g", gemini_api_key="", data_dir=tmp_path, _env_file=None)
    respx.post(GROQ).mock(return_value=httpx.Response(503))
    with pytest.raises(LLMError):
        LLMRouter(conn, s).complete_json("classify", "s", "u")
    assert no_sleep == [1, 2, 4]


@respx.mock
def test_invalid_json_raises_llmerror(conn, tmp_path):
    s = Settings(groq_api_key="g", gemini_api_key="", data_dir=tmp_path, _env_file=None)
    respx.post(GROQ).mock(return_value=groq_ok("not json"))
    with pytest.raises(LLMError):
        LLMRouter(conn, s).complete_json("classify", "s", "u")


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
        assert list_price_usd("openai/gpt-oss-120b", 1_000_000, 1_000_000) == 0.75
    assert caplog.text == ""


def test_every_default_model_has_a_list_price():
    from finn.config import ROUTES, route_for
    from finn.llm.costs import LIST_PRICES_PER_MTOK

    s = Settings(_env_file=None)
    assert {route_for(t, s)[1] for t in ROUTES} <= set(LIST_PRICES_PER_MTOK)


@respx.mock
def test_groq_gpt_oss_sends_explicit_reasoning_effort(conn, settings):
    route = respx.post(GROQ).mock(return_value=groq_ok())
    LLMRouter(conn, settings).complete_json("classify", "sys", "usr")
    body = json.loads(route.calls[0].request.content)
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["reasoning_effort"] == "medium"


@respx.mock
def test_groq_non_reasoning_model_omits_reasoning_effort(conn, tmp_path):
    s = Settings(
        groq_api_key="g", data_dir=tmp_path, finn_model_classify="allam-2-7b", _env_file=None
    )
    route = respx.post(GROQ).mock(return_value=groq_ok())
    LLMRouter(conn, s).complete_json("classify", "sys", "usr")
    assert "reasoning_effort" not in json.loads(route.calls[0].request.content)


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
def test_gemini_safety_block_raises_clear_error(conn, tmp_path, no_sleep, body, needle):
    s = Settings(groq_api_key="", gemini_api_key="m", data_dir=tmp_path, _env_file=None)
    route = respx.post(GEMINI).mock(return_value=gemini_resp(body))
    with pytest.raises(LLMError, match=needle):
        LLMRouter(conn, s).complete_json("extract_transcript", "s", "u")
    assert route.call_count == 1 and no_sleep == []


@respx.mock
def test_invalid_json_still_logs_usage(conn, tmp_path):
    s = Settings(groq_api_key="g", gemini_api_key="", data_dir=tmp_path, _env_file=None)
    respx.post(GROQ).mock(return_value=groq_ok("not json"))
    r = LLMRouter(conn, s)
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


def gemini_ok(content='{"a": 1}'):
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"parts": [{"text": content}]}}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2},
        },
    )


def test_chain_for_appends_fallbacks(settings):
    assert chain_for("classify", settings) == [
        ("groq", "openai/gpt-oss-120b"),
        ("gemini", "gemini-3.5-flash-lite"),
    ]


def test_chain_for_dedupes_primary_and_fallback(tmp_path):
    s = Settings(finn_model_extract_transcript="gemini-3.5-flash-lite", _env_file=None)
    assert chain_for("extract_transcript", s) == [
        ("gemini", "gemini-3.5-flash-lite"),
        ("groq", "openai/gpt-oss-120b"),
    ]


@respx.mock
def test_falls_back_to_gemini_on_groq_5xx(conn, settings, no_sleep):
    groq = respx.post(GROQ).mock(return_value=httpx.Response(503))
    respx.post(GEMINI).mock(return_value=gemini_ok())
    r = LLMRouter(conn, settings)
    assert r.complete_json("classify", "s", "u") == {"a": 1}
    assert groq.call_count == 2
    assert no_sleep == [1]
    assert r.last_model == "gemini/gemini-3.5-flash-lite"


@respx.mock
def test_rate_limit_waits_on_primary_instead_of_failing_over(conn, settings, no_sleep):
    limited = httpx.Response(429, headers={"retry-after": "7"})
    groq = respx.post(GROQ).mock(side_effect=[limited, limited, groq_ok()])
    gem = respx.post(GEMINI).mock(return_value=gemini_ok())
    r = LLMRouter(conn, settings)
    assert r.complete_json("classify", "s", "u") == {"a": 1}
    assert groq.call_count == 3 and gem.call_count == 0
    assert no_sleep == [7, 7]
    assert r.last_model == "groq/openai/gpt-oss-120b"


@respx.mock
def test_rate_limit_budget_is_separate_from_outage_budget(conn, settings, no_sleep):
    limited = httpx.Response(429, headers={"retry-after": "7"})
    groq = respx.post(GROQ).mock(side_effect=[limited, httpx.Response(503), limited, groq_ok()])
    gem = respx.post(GEMINI).mock(return_value=gemini_ok())
    assert LLMRouter(conn, settings).complete_json("classify", "s", "u") == {"a": 1}
    assert groq.call_count == 4 and gem.call_count == 0
    assert no_sleep == [7, 1, 7]


@respx.mock
def test_persistent_rate_limit_fails_over_after_its_budget(conn, settings, no_sleep):
    groq = respx.post(GROQ).mock(return_value=httpx.Response(429, headers={"retry-after": "7"}))
    gem = respx.post(GEMINI).mock(return_value=gemini_ok())
    assert LLMRouter(conn, settings).complete_json("classify", "s", "u") == {"a": 1}
    assert groq.call_count == 4 and gem.call_count == 1
    assert no_sleep == [7, 7, 7]


@respx.mock
def test_invalid_escape_is_repaired_once(conn, tmp_path):
    s = Settings(groq_api_key="g", gemini_api_key="", data_dir=tmp_path, _env_file=None)
    # \' is not a JSON escape (a gpt-oss slip); the valid \\ beside it must survive
    respx.post(GROQ).mock(return_value=groq_ok(r'{"a": "x\'y", "b": "c:\\d"}'))
    out = LLMRouter(conn, s).complete_json("classify", "s", "u")
    assert out == {"a": "x\\'y", "b": "c:\\d"}


def test_parse_json_repairs_invalid_escape():
    assert router_mod._parse_json(r'{"a": "x\'y"}') == {"a": "x\\'y"}
    assert router_mod._parse_json(r'{"a": "\\\q"}') == {"a": "\\\\q"}


@pytest.mark.parametrize("text", [r'{"a": "x\'y"', "not json", r'{"a": "\q", }'])
def test_parse_json_still_rejects_truly_invalid_json(text):
    with pytest.raises(LLMError, match="invalid JSON"):
        router_mod._parse_json(text)


@respx.mock
def test_falls_back_on_invalid_json(conn, settings):
    respx.post(GROQ).mock(return_value=groq_ok("not json"))
    respx.post(GEMINI).mock(return_value=gemini_ok('{"b": 2}'))
    assert LLMRouter(conn, settings).complete_json("classify", "s", "u") == {"b": 2}


@respx.mock
def test_missing_primary_key_goes_straight_to_fallback(conn, tmp_path):
    s = Settings(groq_api_key="", gemini_api_key="m", data_dir=tmp_path, _env_file=None)
    groq = respx.post(GROQ).mock(return_value=groq_ok())
    gem = respx.post(GEMINI).mock(return_value=gemini_ok())
    assert LLMRouter(conn, s).complete_json("classify", "s", "u") == {"a": 1}
    assert groq.call_count == 0 and gem.call_count == 1


@respx.mock
def test_last_usable_model_gets_full_retries(conn, tmp_path, no_sleep):
    s = Settings(groq_api_key="", gemini_api_key="m", data_dir=tmp_path, _env_file=None)
    gem = respx.post(GEMINI).mock(return_value=httpx.Response(503))
    with pytest.raises(LLMError):
        LLMRouter(conn, s).complete_json("classify", "s", "u")
    assert gem.call_count == 4 and no_sleep == [1, 2, 4]


@respx.mock
def test_cached_fallback_answer_skips_http(conn, settings):
    groq = respx.post(GROQ).mock(return_value=httpx.Response(503))
    gem = respx.post(GEMINI).mock(return_value=gemini_ok())
    r = LLMRouter(conn, settings)
    r.complete_json("classify", "s", "u")
    r.last_model = None
    assert r.complete_json("classify", "s", "u") == {"a": 1}
    assert groq.call_count == 2 and gem.call_count == 1
    assert r.last_model == "gemini/gemini-3.5-flash-lite"


@respx.mock
def test_all_models_fail_names_each(conn, settings):
    respx.post(GROQ).mock(return_value=httpx.Response(503))
    respx.post(GEMINI).mock(return_value=httpx.Response(503))
    with pytest.raises(LLMError) as ei:
        LLMRouter(conn, settings).complete_json("classify", "s", "u")
    assert "groq/openai/gpt-oss-120b" in str(ei.value)
    assert "gemini/gemini-3.5-flash-lite" in str(ei.value)


def quota_429():
    return httpx.Response(429, headers={"retry-after": "781"})


@respx.mock
def test_quota_429_fails_over_without_sleeping(conn, settings, no_sleep):
    groq = respx.post(GROQ).mock(return_value=quota_429())
    respx.post(GEMINI).mock(return_value=gemini_ok())
    assert LLMRouter(conn, settings).complete_json("classify", "s", "u") == {"a": 1}
    assert no_sleep == []
    assert groq.call_count == 1


@respx.mock
def test_exhausted_provider_is_skipped_on_later_calls(conn, settings, no_sleep):
    groq = respx.post(GROQ).mock(return_value=quota_429())
    gem = respx.post(GEMINI).mock(return_value=gemini_ok())
    r = LLMRouter(conn, settings)
    r.complete_json("classify", "s", "u")
    assert r.complete_json("classify", "s", "other") == {"a": 1}
    assert groq.call_count == 1 and gem.call_count == 2
    assert no_sleep == []


@respx.mock
def test_quota_on_one_model_keeps_sibling_model_usable(conn, settings, monkeypatch):
    monkeypatch.setattr(
        router_mod, "chain_for", lambda task, s: [("gemini", "model-a"), ("gemini", "model-b")]
    )
    url = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
    a = respx.post(url.format("model-a")).mock(return_value=quota_429())
    b = respx.post(url.format("model-b")).mock(return_value=gemini_ok())
    r = LLMRouter(conn, settings)
    assert r.complete_json("classify", "s", "u") == {"a": 1}
    assert r.complete_json("classify", "s", "other") == {"a": 1}
    assert a.call_count == 1 and b.call_count == 2


@respx.mock
def test_exhausted_provider_returns_after_reset(conn, settings, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(router_mod, "_now", lambda: now[0])
    groq = respx.post(GROQ).mock(side_effect=[quota_429(), groq_ok()])
    respx.post(GEMINI).mock(return_value=gemini_ok('{"b": 2}'))
    r = LLMRouter(conn, settings)
    assert r.complete_json("classify", "s", "u") == {"b": 2}
    now[0] += 780
    assert r.complete_json("classify", "s", "v") == {"b": 2}
    assert groq.call_count == 1
    now[0] += 2
    assert r.complete_json("classify", "s", "w") == {"a": 1}
    assert groq.call_count == 2


@respx.mock
def test_quota_on_last_model_raises_fast(conn, tmp_path, no_sleep):
    s = Settings(groq_api_key="g", gemini_api_key="", data_dir=tmp_path, _env_file=None)
    groq = respx.post(GROQ).mock(return_value=quota_429())
    with pytest.raises(LLMError, match="quota exhausted"):
        LLMRouter(conn, s).complete_json("classify", "s", "u")
    assert no_sleep == [] and groq.call_count == 1


@respx.mock
def test_non_numeric_retry_after_is_pacing(conn, settings, no_sleep):
    date = "Wed, 21 Oct 2026 07:28:00 GMT"
    groq = respx.post(GROQ).mock(
        side_effect=[httpx.Response(429, headers={"retry-after": date}), groq_ok()]
    )
    gem = respx.post(GEMINI).mock(return_value=gemini_ok())
    assert LLMRouter(conn, settings).complete_json("classify", "s", "u") == {"a": 1}
    assert groq.call_count == 2 and gem.call_count == 0
    assert no_sleep == [1]
