"""The tool loop: let the model ask for calculations, run them, hand back the answers.

How a tool call works, step by step:
1. We send the conversation plus a menu of tools to the model.
2. The model replies either with normal text (it is done) or with a request such as
   "run cost_per_use with these arguments". The model never runs anything itself.
3. Our code runs the real Python function and adds the result to the conversation.
4. We ask the model again. It now has exact numbers to work with.
5. Repeat until the model stops asking, or we hit the step limit.

Code also enforces three rules the prompt can only suggest:
- A `required` tool must actually get used. If the model tries to finish without it, we remind it.
- Code decides when the job is done. Once every required tool has succeeded, the loop ends.
  In testing, a small model that was asked "are you done?" kept re-requesting the same
  calculations instead of stopping, so we stop asking.
- No repeats. Small models sometimes ask for the same calculation over and over. An identical
  repeat is not run again, and if a whole turn is repeats the loop stops.
"""

import json
import time

import config
from agents.base import default_chat
from tools.registry import run_tool, tool_specs


def assistant_message(message) -> dict:
    """Turn the model's reply into a plain dict we can put back into the conversation."""
    entry = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        entry["tool_calls"] = [
            {"function": {"name": call.function.name, "arguments": call.function.arguments}}
            for call in message.tool_calls
        ]
    return entry


def tool_result_text(record: dict) -> str:
    """What the model reads after a tool runs: the result, or what went wrong."""
    if record["ok"]:
        return json.dumps(record["result"])
    return f"Error: {record['error']}. Fix the arguments and call the tool again."


def run_tool_phase(
    messages: list[dict],
    chat=default_chat,
    tool_names: list[str] | None = None,
    required: tuple[str, ...] = (),
    max_steps: int = config.MAX_TOOL_STEPS,
    max_nudges: int = config.MAX_TOOL_NUDGES,
    on_tool_call=None,
) -> dict:
    """Run the loop. Adds every model reply and tool result to `messages` (the caller's list).
    Returns a trace: model_calls, tool_calls, nudges, stopped, missing_required.
    `stopped` says why it ended: requirements_met, model_finished, repeating, or max_steps.
    `on_tool_call`, if given, is called with each tool record right after the tool runs."""
    specs = tool_specs(tool_names)
    model_calls, tool_calls = [], []
    succeeded = set()
    already_run = {}  # (tool name, arguments) -> the record from the first time it ran
    nudges = 0
    stopped = "max_steps"

    for step in range(1, max_steps + 1):
        started = time.perf_counter()
        response = chat(
            model=config.MODEL,
            messages=messages,
            tools=specs,
            options=config.chat_options(config.MAX_TOOL_TURN_TOKENS, config.TOOL_TEMPERATURE),
        )
        message = response.message
        requests = message.tool_calls or []
        model_calls.append({
            "step": step,
            "seconds": round(time.perf_counter() - started, 2),
            "prompt_tokens": getattr(response, "prompt_eval_count", None),
            "output_tokens": getattr(response, "eval_count", None),
            "cut_off": getattr(response, "done_reason", None) == "length",
            "content": message.content,
            "tool_calls_requested": len(requests),
        })
        messages.append(assistant_message(message))

        if not requests:
            missing = [name for name in required if name not in succeeded]
            if missing and nudges < max_nudges:
                nudges += 1
                messages.append({
                    "role": "user",
                    "content": f"You have not used {', '.join(missing)} yet. Call it now, then continue.",
                })
                continue
            stopped = "model_finished"
            break

        repeats = 0
        failures = 0
        for call in requests:
            key = (call.function.name, json.dumps(call.function.arguments, sort_keys=True, default=str))
            if key in already_run:
                repeats += 1
                record = already_run[key]
                tool_calls.append({"step": step, **record, "duplicate": True})
                content = (
                    "You already made this exact call. The result was: "
                    f"{json.dumps(record['result'])}. Do not call it again. Use it and write your final reply."
                )
            else:
                record = run_tool(call.function.name, call.function.arguments)
                tool_calls.append({"step": step, **record, "duplicate": False})
                if on_tool_call:
                    on_tool_call(record)
                if record["ok"]:
                    succeeded.add(record["tool"])
                    already_run[key] = record
                else:
                    failures += 1
                content = tool_result_text(record)
            messages.append({"role": "tool", "tool_name": call.function.name, "content": content})

        if required and not failures and all(name in succeeded for name in required):
            stopped = "requirements_met"
            break

        if repeats == len(requests):  # nothing new this turn: the model is going in circles
            stopped = "repeating"
            break

    return {
        "model_calls": model_calls,
        "tool_calls": tool_calls,
        "nudges": nudges,
        "stopped": stopped,
        "missing_required": [name for name in required if name not in succeeded],
    }
