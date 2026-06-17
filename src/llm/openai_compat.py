import json
from dataclasses import dataclass, field
from typing import Any
from openai import OpenAI
from .base import LLMAdapter


@dataclass
class LLMResponse:
    content: str | None
    finish_reason: str
    tool_calls: list | None
    _raw_tool_calls: Any = field(default=None, repr=False)

    def assistant_message(self) -> dict:
        """构造追加回 messages 的 assistant 消息"""
        msg: dict = {"role": "assistant"}
        if self.content:
            msg["content"] = self.content
        if self._raw_tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self._raw_tool_calls
            ]
        return msg

    @property
    def has_tool_calls(self) -> bool:
        return bool(self._raw_tool_calls)


class OpenAICompatAdapter(LLMAdapter):
    def __init__(self, config: dict):
        self.client = OpenAI(
            api_key=config["api_key"],
            base_url=config.get("base_url", "https://api.openai.com/v1"),
            timeout=config.get("timeout", 90),  # 单次 LLM 调用最长 90s，防止 API 挂死
        )
        self.model = config.get("model", "gpt-4o")
        self.temperature = config.get("temperature", 0.3)
        self.max_tokens = config.get("max_tokens", 4096)

    def chat(self, messages: list[dict], **kwargs) -> str:
        params: dict = dict(
            model=kwargs.get("model", self.model),
            messages=messages,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
        )
        if kwargs.get("enable_search"):
            params["extra_body"] = {"enable_search": True}
        response = self.client.chat.completions.create(**params)
        return response.choices[0].message.content or ""

    def chat_with_tools(self, messages: list[dict], tools: list[dict], max_tokens: int | None = None) -> LLMResponse:
        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message
        return LLMResponse(
            content=msg.content,
            finish_reason=choice.finish_reason or "stop",
            tool_calls=msg.tool_calls,
            _raw_tool_calls=msg.tool_calls,
        )


def create_llm(config: dict) -> LLMAdapter:
    provider = config.get("provider", "openai_compat")
    if provider == "openai_compat":
        return OpenAICompatAdapter(config)
    raise ValueError(f"不支持的 LLM provider: {provider}")
