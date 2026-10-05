from datetime import datetime

from app.db.models import Email


def make_email(subject: str, body: str, sender: str = "Sender <s@example.com>", received: datetime | None = None) -> Email:
    return Email(id=1, external_id="t", thread_id="t", sender=sender, recipients=["me@example.com"],
                 subject=subject, body=body, received_at=received or datetime(2026, 10, 4, 9, 0))
