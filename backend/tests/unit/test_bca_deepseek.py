from __future__ import annotations

import sys
from types import SimpleNamespace

from backend.app.three_d_agent.config import Settings
from backend.app.three_d_agent.providers.deepseek import DeepSeekBriefEnricher


def test_structured_deepseek_requests_disable_thinking(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def with_structured_output(self, schema, *, method: str):
            assert method == "json_mode"
            return self

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=FakeChatOpenAI))

    provider = DeepSeekBriefEnricher(Settings(deepseek_api_key="test-key"))
    provider._model(object())

    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}
