import json
from pathlib import Path
from types import SimpleNamespace

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"


class FakeClient:
    """Stands in for anthropic.Anthropic: returns recorded tool calls in order and logs requests."""

    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        data = self.responses.pop(0)
        block = SimpleNamespace(type="tool_use", id=f"toolu_{len(self.calls)}", name="record_study_notes", input=data)
        return SimpleNamespace(content=[block], stop_reason="tool_use")


@pytest.fixture
def sample_notes() -> list[dict]:
    return json.loads((FIXTURES / "sample_notes.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_vtt() -> Path:
    return EXAMPLES / "cafe-du-lundi.vtt"


@pytest.fixture
def fake_client():
    return FakeClient
