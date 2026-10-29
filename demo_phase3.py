"""Phase 3 demo: The Analyst uses calculator tools, then gives a structured take.

Run with:  .venv/bin/python demo_phase3.py
"""

import json

import httpx

from agents.analyst import ANALYST
from agents.base import StructuredOutputError
from agents.council_agent import open_turn
from demo_phase2 import SAMPLES
from display import ProgressChat




def show_trace(trace):
    phase = trace["tool_phase"]
    ran = [call for call in trace["tool_calls"] if not call["duplicate"]]
    skipped = len(trace["tool_calls"]) - len(ran)
    print(f"Tool phase: {len(trace['model_calls'])} model turns, {len(ran)} tool calls run, "
          f"{skipped} identical repeats skipped, {phase['nudges']} reminders, ended: {phase['stopped']}")
    for call in ran:
        args = json.dumps(call["arguments"])
        if len(args) > 120:
            args = args[:117] + "..."
        print(f"  step {call['step']}: {call['tool']}({args})")
        if call["ok"]:
            print(f"           -> {call['result']['summary']}")
        else:
            print(f"           -> REJECTED: {call['error'][:150]}")
    if phase["missing_required"]:
        print(f"  WARNING: never used required tool(s): {', '.join(phase['missing_required'])}")
    for a in trace["attempts"]:
        status = "valid" if a["ok"] else f"rejected: {a['error']}"
        print(f"Final answer attempt {a['attempt']}: {a['seconds']}s, {status}")


def main():
    for purchase in SAMPLES:
        print("=" * 72)
        print(f"{purchase.item} · ${purchase.price:,.0f} · wants it {purchase.want_level}/10")
        print("-" * 72)
        try:
            take, trace, _ = open_turn(ANALYST, purchase, chat=ProgressChat())
        except StructuredOutputError as error:
            print(f"{ANALYST.name} could not produce a valid reply after the tools ran.")
            for a in error.attempts:
                print(f"  attempt {a['attempt']}: rejected: {a['error']}")
            continue
        except httpx.TimeoutException:
            print("The model took too long and was stopped by the timeout.")
            continue
        except ConnectionError:
            print("Can't reach Ollama. Start it with:  brew services start ollama")
            return

        show_trace(trace)
        print(f"\n{ANALYST.name}: {take.take}\n")
        for name, rating in take.ratings:
            print(f"  {name:<14} {rating.score:>2}/10  {rating.reason}")
        print(f"\n  lean: {take.lean.upper()}   confidence: {take.confidence}/10")
    print("=" * 72)


if __name__ == "__main__":
    main()
