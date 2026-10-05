"""Email provider interface (the agent's 'tools'). Agent code depends on this, never on Gmail directly."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


class EmailProviderError(Exception):
    pass


@dataclass
class RawEmail:
    external_id: str
    thread_id: str
    sender: str
    recipients: list[str]
    subject: str
    body: str
    received_at: datetime  # naive UTC


@dataclass
class SendResult:
    ok: bool
    message_id: str | None = None
    detail: dict = field(default_factory=dict)


class EmailProvider(ABC):
    source: str = "unknown"

    @abstractmethod
    def fetch_emails(self, max_results: int = 25) -> list[RawEmail]: ...
    @abstractmethod
    def get_email(self, external_id: str) -> RawEmail | None: ...
    @abstractmethod
    def get_thread(self, thread_id: str) -> list[RawEmail]: ...
    @abstractmethod
    def search_emails(self, query: str, max_results: int = 25) -> list[RawEmail]: ...
    @abstractmethod
    def create_draft(self, to: str, subject: str, body: str, thread_id: str | None = None) -> str | None: ...
    @abstractmethod
    def send_email(self, to: str, subject: str, body: str, thread_id: str | None = None,
                   in_reply_to: str | None = None) -> SendResult: ...
