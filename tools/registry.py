"""The tool shelf: what tools exist, how to describe them to the model, and how to run them safely.

Each tool has a name, a description the model reads, a Pydantic input model, and a
plain Python function. Running a tool never crashes the agent. If the model asks for
a tool that doesn't exist, or passes bad arguments, the problem is returned as text so
the model can read it and try again, the same idea as the retry loop for final answers.
"""

import json
import time
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, ValidationError

from tools.cost_per_use import CostPerUseInput, cost_per_use
from tools.resale import ResaleInput, estimate_resale
from validation import summarize_errors


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    func: Callable[[BaseModel], dict]


TOOLS = {
    tool.name: tool
    for tool in [
        Tool(
            name="cost_per_use",
            description="Calculate what each use of a gadget costs. Do the math here, never in your head.",
            input_model=CostPerUseInput,
            func=cost_per_use,
        ),
        Tool(
            name="estimate_resale",
            description="Estimate what a gadget could resell for after some years. Returns a rough, unverified estimate.",
            input_model=ResaleInput,
            func=estimate_resale,
        ),
    ]
}


def plain_property(schema: dict) -> dict:
    """An optional argument, written by Pydantic as anyOf: [the real type, null], as just the real type.

    The Ollama client keeps only type, description, enum and items of each argument and drops the
    rest without a word. So an optional `category` reached the model as a description with no type
    and no list of categories, and the 14B passed `object: "phone"` instead, in 9 of 39 councils
    (24 failed tool calls). Leaving an argument out still means "not given", because the input
    model's default does that, not the schema."""
    options = schema.get("anyOf")
    if not options:
        return schema
    real = [option for option in options if option.get("type") != "null"]
    if len(real) != 1:
        return schema
    rest = {key: value for key, value in schema.items() if key != "anyOf"}
    return {**real[0], **rest}


def tool_parameters(tool: Tool) -> dict:
    schema = tool.input_model.model_json_schema()
    schema["properties"] = {name: plain_property(prop) for name, prop in schema["properties"].items()}
    return schema


def tool_specs(names: list[str] | None = None) -> list[dict]:
    """Describe tools in the format Ollama sends to the model. The argument rules come
    straight from the Pydantic input model, so the description and the validation can't drift."""
    chosen = [TOOLS[name] for name in (names or TOOLS)]
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool_parameters(tool),
            },
        }
        for tool in chosen
    ]


def argument_error(name: str, error: ValidationError) -> str:
    """The short error, plus the tool's real inputs when the model made one up. Live run: told only
    "object: Extra inputs are not permitted", the 14B sent the same call again unchanged."""
    text = summarize_errors(error)
    made_up = [str(item["loc"][-1]) for item in error.errors() if item["type"] == "extra_forbidden"]
    if made_up:
        inputs = ", ".join(TOOLS[name].input_model.model_fields)
        text += f". {name} has no input called {', '.join(made_up)}; its inputs are: {inputs}"
    return text


def run_tool(name: str, arguments) -> dict:
    """Run one tool call. Always returns a record, never raises.
    Record keys: tool, arguments, ok, result, error, seconds."""
    started = time.perf_counter()
    record = {"tool": name, "arguments": arguments, "ok": False, "result": None, "error": None}

    try:
        if name not in TOOLS:
            raise ValueError(f"unknown tool '{name}'. Available tools: {', '.join(TOOLS)}")
        tool = TOOLS[name]

        if isinstance(arguments, str):  # some models send the arguments as a JSON string
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                raise ValueError("arguments must be a JSON object")
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be a JSON object")

        record["result"] = tool.func(tool.input_model.model_validate(arguments))
        record["ok"] = True
    except ValidationError as error:
        record["error"] = argument_error(name, error)
    except ValueError as error:
        record["error"] = str(error)

    record["seconds"] = round(time.perf_counter() - started, 4)
    return record
