from abc import ABC, abstractmethod


class LLMAdapter(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], **kwargs) -> str:
        """发送消息并返回文本响应"""
        pass
