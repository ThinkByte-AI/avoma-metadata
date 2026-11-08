"""Chat model access through the Bedrock Converse API (model-agnostic; default GLM 5)."""
import copy
import itertools
from functools import lru_cache
from typing import Any, Protocol

import boto3
from botocore.config import Config


class ChatModel(Protocol):
    model_id: str

    def converse(self, system: str, messages: list[dict], tools: list[dict] | None, max_tokens: int) -> dict:
        """Returns {"message": <Converse output.message>, "stop_reason": str}."""
        ...


class BedrockChatModel:
    def __init__(self, model_id: str, region: str, client: Any = None):
        self.model_id = model_id
        self.client = client or boto3.client(
            "bedrock-runtime", region_name=region,
            config=Config(retries={"mode": "adaptive", "max_attempts": 4}, read_timeout=120),
        )

    def converse(self, system: str, messages: list[dict], tools: list[dict] | None, max_tokens: int) -> dict:
        kwargs: dict = {
            "modelId": self.model_id,
            "system": [{"text": system}],
            "messages": messages,
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.2},
        }
        if tools:
            kwargs["toolConfig"] = {"tools": tools}
        r = self.client.converse(**kwargs)
        return {"message": r["output"]["message"], "stop_reason": r.get("stopReason", "end_turn")}


_ids = itertools.count(1)


def tool_call(query: str, **inputs: Any) -> dict:
    """Test helper: a scripted assistant turn that calls search_meetings."""
    return {
        "message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": f"tool-{next(_ids)}", "name": "search_meetings", "input": {"query": query, **inputs}}}
        ]},
        "stop_reason": "tool_use",
    }


def final(text: str) -> dict:
    """Test helper: a scripted final assistant answer."""
    return {"message": {"role": "assistant", "content": [{"text": text}]}, "stop_reason": "end_turn"}


class FakeChatModel:
    """Replays scripted turns (dicts, or callables taking the messages). Records every call."""

    model_id = "fake-chat-model"

    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[dict] = []

    def converse(self, system: str, messages: list[dict], tools: list[dict] | None, max_tokens: int) -> dict:
        self.calls.append({"system": system, "messages": copy.deepcopy(messages), "tools": tools})
        if not self.script:
            return final("")
        item = self.script.pop(0)
        return item(messages) if callable(item) else copy.deepcopy(item)


@lru_cache
def get_chat_model() -> ChatModel:
    """FastAPI dependency."""
    from app.config import get_settings  # noqa: PLC0415

    s = get_settings()
    return BedrockChatModel(s.bedrock_chat_model, s.aws_region)
