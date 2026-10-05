from sqlalchemy.orm import Session

from app.ai.schemas import Category, Priority
from app.db.repositories import PreferenceRepository

DEFAULT_SETTINGS = {"notify_urgent": "true", "notify_action_required": "true", "notify_reply_ready": "true"}


class PreferenceError(ValueError):
    pass


class PreferenceService:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.repo = PreferenceRepository(db, user_id)

    def priority_rules(self) -> dict[str, str]:
        return self.repo.by_kind("priority_rule")

    def settings(self) -> dict[str, str]:
        return {**DEFAULT_SETTINGS, **self.repo.by_kind("setting")}

    def update(self, priority_rules: dict[str, str | None] | None, settings: dict[str, bool] | None) -> None:
        for cat, prio in (priority_rules or {}).items():
            if cat not in Category._value2member_map_:
                raise PreferenceError(f"Unknown category: {cat}")
            if prio is None or prio == "":
                self.repo.delete("priority_rule", cat)
            elif prio in Priority._value2member_map_:
                self.repo.upsert("priority_rule", cat, prio)
            else:
                raise PreferenceError(f"Unknown priority: {prio}")
        for key, val in (settings or {}).items():
            if key not in DEFAULT_SETTINGS:
                raise PreferenceError(f"Unknown setting: {key}")
            self.repo.upsert("setting", key, "true" if val else "false")
        self.db.commit()
