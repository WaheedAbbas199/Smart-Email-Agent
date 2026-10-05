import base64
import json

import httpx
import pytest

from app.integrations.gmail import GmailProvider, build_raw_message, parse_message
from app.integrations.provider import EmailProviderError


def b64(s):
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


MSG = {"id": "m1", "threadId": "t1", "payload": {
    "mimeType": "multipart/alternative",
    "headers": [{"name": "From", "value": "Sam <sam@x.com>"}, {"name": "To", "value": "me@x.com"},
                {"name": "Subject", "value": "Hello"}, {"name": "Date", "value": "Mon, 05 Oct 2026 10:00:00 +0000"}],
    "parts": [{"mimeType": "text/plain", "body": {"data": b64("Plain body")}},
              {"mimeType": "text/html", "body": {"data": b64("<p>HTML body</p>")}}]}}


def test_parse_message_prefers_plain():
    e = parse_message(MSG)
    assert (e.external_id, e.thread_id, e.subject, e.body) == ("m1", "t1", "Hello", "Plain body")
    assert e.recipients == ["me@x.com"] and e.received_at.hour == 10


def test_html_fallback_strips_tags():
    m = json.loads(json.dumps(MSG))
    m["payload"]["parts"] = [m["payload"]["parts"][1]]
    assert parse_message(m).body == "HTML body"


def test_send_single_attempt_and_payload():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={"id": "sent1", "threadId": "t1"})

    p = GmailProvider("tok", httpx.Client(transport=httpx.MockTransport(handler)))
    res = p.send_email("a@b.c", "Re: Hi", "Body", thread_id="t1")
    assert res.ok and res.message_id == "sent1" and len(calls) == 1
    assert calls[0].headers["authorization"] == "Bearer tok"
    sent = json.loads(calls[0].content)
    assert sent["threadId"] == "t1"
    assert b"Body" in base64.urlsafe_b64decode(sent["raw"] + "==")


def test_failed_send_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500)

    p = GmailProvider("tok", httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(EmailProviderError):
        p.send_email("a@b.c", "s", "b")
    assert len(calls) == 1


def test_expired_token_message():
    p = GmailProvider("tok", httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    with pytest.raises(EmailProviderError, match="reconnect"):
        p.fetch_emails()


def test_raw_message_has_reply_headers():
    raw = base64.urlsafe_b64decode(build_raw_message("a@b.c", "S", "B", "<id1>") + "==").decode()
    assert "In-Reply-To: <id1>" in raw
