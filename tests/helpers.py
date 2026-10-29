"""Shared test helpers: a fake stand-in for the model."""

import copy
from types import SimpleNamespace


def tool_request(name: str, arguments):
    """A scripted reply in which the model asks for one tool."""
    call = SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))
    return SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[call]), eval_count=10)


def cut_off(text: str):
    """A scripted reply that hit the length limit partway through."""
    return SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None), eval_count=800, done_reason="length")


class FakeChat:
    """Stands in for ollama.chat. Hands back scripted replies in order and remembers
    exactly what it was sent each time. A reply is either plain text (the model just
    talks) or a tool_request(...) (the model asks for a tool)."""

    def __init__(self, replies: list):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        reply = self.replies.pop(0)
        if isinstance(reply, str):
            return SimpleNamespace(message=SimpleNamespace(content=reply, tool_calls=None), eval_count=10, done_reason="stop")
        return reply
