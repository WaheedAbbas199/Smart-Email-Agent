import json
from datetime import date

import httpx
import pytest

from app.ai.gemini_client import GeminiClient
from app.ai.llm_base import LLMError, LLMOutputError

PAYLOAD = {"sender": "a@b.c", "recipients": [], "subject": "s", "body": "b", "received_at": ""}


def make(handler, retries=2):
    return GeminiClient("k", "m", max_retries=retries, backoff=0, client=httpx.Client(transport=httpx.MockTransport(handler)))


def ok(text):
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def test_valid_json_parsed_and_key_sent_in_header_only():
    seen = {}

    def handler(req):
        seen["h"], seen["url"], seen["body"] = req.headers, str(req.url), json.loads(req.content)
        return ok('```json\n{"category":"job","priority":"high","summary":"x","action_required":true}\n```')

    r = make(handler).analyze_email(PAYLOAD, {}, date(2026, 10, 4))
    assert r.category.value == "job" and r.action_required
    assert seen["h"]["x-goog-api-key"] == "k" and "key=" not in seen["url"]
    assert "<email_content>" in seen["body"]["contents"][0]["parts"][0]["text"]  # email is delimited data


def test_invalid_json_raises_output_error():
    with pytest.raises(LLMOutputError):
        make(lambda r: ok("not json")).analyze_email(PAYLOAD, {}, date(2026, 10, 4))


def test_retries_on_429_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429) if len(calls) < 3 else ok('{"category":"work"}')

    assert make(handler).analyze_email(PAYLOAD, {}, date(2026, 10, 4)).category.value == "work"
    assert len(calls) == 3


def test_no_retry_on_client_error():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(400)

    with pytest.raises(LLMError):
        make(handler).analyze_email(PAYLOAD, {}, date(2026, 10, 4))
    assert len(calls) == 1


def test_blocked_response_raises():
    with pytest.raises(LLMOutputError):
        make(lambda r: httpx.Response(200, json={"candidates": []})).draft_reply(PAYLOAD, {})
