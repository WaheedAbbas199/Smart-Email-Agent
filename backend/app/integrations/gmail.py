"""Gmail REST API adapter (OAuth access token supplied by the service layer)."""
import base64
import re
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime

import httpx

from app.integrations.provider import EmailProvider, EmailProviderError, RawEmail, SendResult

API = "https://gmail.googleapis.com/gmail/v1/users/me"


def _b64(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def extract_body(payload: dict) -> str:
    """Prefer text/plain; fall back to stripped text/html; walk multipart recursively."""
    plain, html = [], []

    def walk(part: dict):
        mime, data = part.get("mimeType", ""), part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_b64(data))
        elif data and mime == "text/html":
            html.append(_strip_html(_b64(data)))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    return "\n".join(plain) if plain else "\n".join(html)


def parse_message(msg: dict) -> RawEmail:
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    try:
        received = parsedate_to_datetime(headers["date"]).astimezone(timezone.utc).replace(tzinfo=None)
    except (KeyError, TypeError, ValueError):
        received = datetime.fromtimestamp(int(msg.get("internalDate", 0)) / 1000, tz=timezone.utc).replace(tzinfo=None)
    recipients = [addr for _, addr in getaddresses([headers.get("to", ""), headers.get("cc", "")]) if addr]
    return RawEmail(
        external_id=msg["id"], thread_id=msg.get("threadId", ""), sender=headers.get("from", ""),
        recipients=recipients, subject=headers.get("subject", ""), body=extract_body(msg.get("payload", {})),
        received_at=received,
    )


def build_raw_message(to: str, subject: str, body: str, in_reply_to: str | None = None) -> str:
    msg = EmailMessage()
    msg["To"], msg["Subject"] = to, subject
    if in_reply_to:
        msg["In-Reply-To"] = msg["References"] = in_reply_to
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


class GmailProvider(EmailProvider):
    source = "gmail"

    def __init__(self, access_token: str, client: httpx.Client | None = None):
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._client = client or httpx.Client(timeout=20.0)

    def _request(self, method: str, path: str, **kw) -> dict:
        try:
            resp = self._client.request(method, f"{API}{path}", headers=self._headers, **kw)
        except httpx.HTTPError as exc:
            raise EmailProviderError(f"Gmail network error: {type(exc).__name__}") from exc
        if resp.status_code == 401:
            raise EmailProviderError("Gmail token invalid or expired; reconnect your account")
        if resp.status_code >= 400:
            raise EmailProviderError(f"Gmail API error: HTTP {resp.status_code}")
        return resp.json()

    def _list(self, params: dict) -> list[RawEmail]:
        ids = self._request("GET", "/messages", params=params).get("messages", [])
        return [self._get(m["id"]) for m in ids]

    def _get(self, message_id: str) -> RawEmail:
        return parse_message(self._request("GET", f"/messages/{message_id}", params={"format": "full"}))

    def fetch_emails(self, max_results: int = 25):
        return self._list({"maxResults": max_results, "labelIds": "INBOX"})

    def get_email(self, external_id: str):
        return self._get(external_id)

    def get_thread(self, thread_id: str):
        data = self._request("GET", f"/threads/{thread_id}", params={"format": "full"})
        return [parse_message(m) for m in data.get("messages", [])]

    def search_emails(self, query: str, max_results: int = 25):
        return self._list({"maxResults": max_results, "q": query})

    def create_draft(self, to, subject, body, thread_id=None):
        message = {"raw": build_raw_message(to, subject, body)}
        if thread_id:
            message["threadId"] = thread_id
        return self._request("POST", "/drafts", json={"message": message}).get("id")

    def send_email(self, to, subject, body, thread_id=None, in_reply_to=None) -> SendResult:
        """Single attempt only: never retried automatically (could duplicate the email)."""
        payload = {"raw": build_raw_message(to, subject, body, in_reply_to)}
        if thread_id:
            payload["threadId"] = thread_id
        data = self._request("POST", "/messages/send", json=payload)
        return SendResult(ok=True, message_id=data.get("id"), detail={"thread_id": data.get("threadId")})
