"""The one function every agent uses to ask the model for a structured answer.

Two layers keep the output honest:
1. Ollama's `format` option hands the model our JSON schema, and Ollama only lets
   it produce text that fits that shape. That stops most garbage at the source.
2. Pydantic then checks every rule. If anything is wrong, we show the model
   exactly what broke and let it try again, up to MAX_ATTEMPTS times.

Every attempt is recorded, so later phases can save a full trace of each call.
"""

import time

import ollama
from pydantic import BaseModel, ValidationError

import config
from validation import summarize_errors

# One shared client with a timeout, so a stuck call fails instead of hanging forever.
client = ollama.Client(timeout=config.REQUEST_TIMEOUT_SECONDS)
default_chat = client.chat


class StructuredOutputError(Exception):
    """The model failed to produce valid output after every attempt."""

    def __init__(self, message: str, attempts: list[dict]):
        super().__init__(message)
        self.attempts = attempts
        self.trace = None  # callers with more context, such as an agent's turn, attach the full trace here


def call_structured_from_messages(
    messages: list[dict],
    schema: type[BaseModel],
    chat=default_chat,
    max_attempts: int = config.MAX_ATTEMPTS,
    context: dict | None = None,
    max_tokens: int = config.MAX_ANSWER_TOKENS,
    temperature: float = config.TEMPERATURE,
) -> tuple[BaseModel, list[dict]]:
    """Continue an existing conversation and get back a reply shaped like `schema`.
    Returns (validated reply, attempt log). The caller's message list is not changed.

    `chat` is the function that actually talks to the model. It defaults to the real
    Ollama client; tests pass in a fake so they can check the logic without a model.

    `context` is extra information some rules need to do their check, such as who is
    speaking in a rebuttal. Pydantic hands it to the schema's validators.
    """
    messages = list(messages)
    attempts = []

    for attempt in range(1, max_attempts + 1):
        started = time.perf_counter()
        response = chat(
            model=config.MODEL,
            messages=messages,
            format=schema.model_json_schema(),
            options=config.chat_options(max_tokens, temperature),
        )
        raw = response.message.content
        record = {
            "attempt": attempt,
            "seconds": round(time.perf_counter() - started, 2),
            "prompt_tokens": getattr(response, "prompt_eval_count", None),
            "output_tokens": getattr(response, "eval_count", None),
            "cut_off": getattr(response, "done_reason", None) == "length",
            "raw": raw,
        }

        try:
            value = schema.model_validate_json(raw, context=context)
        except ValidationError as error:
            problem = summarize_errors(error)
            if record["cut_off"]:
                problem += " (your reply hit the length limit and was cut off, so keep every field short)"
            attempts.append({**record, "ok": False, "error": problem})
            # Keep the bad reply in the conversation and say what was wrong with it.
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"That reply broke these rules: {problem}. "
                "Send the complete corrected JSON and nothing else.",
            })
            continue

        attempts.append({**record, "ok": True, "error": None})
        return value, attempts

    raise StructuredOutputError(f"No valid reply after {max_attempts} attempts", attempts)


def call_structured(
    system_prompt: str,
    user_prompt: str,
    schema: type[BaseModel],
    chat=default_chat,
    max_attempts: int = config.MAX_ATTEMPTS,
    **settings,
) -> tuple[BaseModel, list[dict]]:
    """The simple case: one system prompt, one user prompt, one structured reply.
    `settings` passes context, max_tokens or temperature through unchanged."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return call_structured_from_messages(messages, schema, chat=chat, max_attempts=max_attempts, **settings)
