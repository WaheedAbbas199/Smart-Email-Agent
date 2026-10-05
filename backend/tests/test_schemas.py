import pytest
from pydantic import ValidationError

from app.ai.schemas import Category, EmailAnalysisResult, Priority


def test_unknown_enums_fall_back_safely():
    r = EmailAnalysisResult.model_validate({"category": "weird", "priority": "ASAP"})
    assert r.category == Category.other and r.priority == Priority.low


def test_confidence_range_enforced():
    with pytest.raises(ValidationError):
        EmailAnalysisResult.model_validate({"category_confidence": 1.7})


def test_bad_deadline_time_dropped():
    assert EmailAnalysisResult.model_validate({"deadline_time": "25:99"}).deadline_time is None
    assert EmailAnalysisResult.model_validate({"deadline_time": "9:05"}).deadline_time == "09:05"


def test_lists_coerced():
    r = EmailAnalysisResult.model_validate({"action_items": "not a list", "key_points": [1, 2]})
    assert r.action_items == [] and r.key_points == ["1", "2"]
