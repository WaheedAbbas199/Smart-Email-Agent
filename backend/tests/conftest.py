import os
from pathlib import Path

# Must be set before the app is imported.
_DB = Path(__file__).parent / "test.db"
if _DB.exists():
    _DB.unlink()
os.environ.update({"DATABASE_URL": f"sqlite:///{_DB}", "LLM_PROVIDER": "mock", "DEMO_MODE": "true",
                   "APP_ENV": "test", "RATE_LIMIT_PER_MINUTE": "100000", "GEMINI_API_KEY": ""})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def agent():
    from app.agents.email_agent import EmailAgent
    from app.ai.mock_llm import MockLLM
    return EmailAgent(MockLLM())
