"""How a council run looks on the screen: live progress lines, each member's turn, and the verdict card.

The orchestrator never prints. It reports what happens through an `on_event` callback, and this file
turns those events into text. `ask.py` and the phase demos share it, so a run looks the same everywhere.
The web UI (phase 7) will do the same job from the saved transcript instead of a live run.
"""

import json
import time

import config
from agents.base import default_chat
from agents.schemas import AgentRebuttal


class ProgressChat:
    """Wraps the real model call and prints a line as each one finishes, so you can
    watch the work happen instead of staring at a silent screen."""

    def __init__(self):
        self.count = 0

    def __call__(self, **kwargs):
        self.count += 1
        kind = "tool turn" if "tools" in kwargs else "final answer"
        print(f"  model call {self.count} ({kind}) ...", end="", flush=True)
        started = time.perf_counter()
        response = default_chat(**kwargs)
        cut = "  CUT OFF at the length limit" if getattr(response, "done_reason", None) == "length" else ""
        print(f" {time.perf_counter() - started:.1f}s, {getattr(response, 'eval_count', '?')} tokens{cut}", flush=True)
        return response


def show_attempts(trace):
    phase = trace.get("tool_phase")
    if phase and phase["nudges"]:
        print(f"    reminded to use its tool {phase['nudges']} time(s)")
    if phase and phase["missing_required"]:
        print(f"    WARNING: never used required tool(s): {', '.join(phase['missing_required'])}")
    for a in trace.get("attempts", []):
        status = "valid" if a["ok"] else f"rejected: {a['error']}"
        print(f"    answer attempt {a['attempt']}: {status}")
    if trace.get("error"):
        print(f"    error: {trace['error']}")


def show_reply(turn):
    reply = turn.reply
    if isinstance(reply, AgentRebuttal):
        print(f"\n  -> answering {', '.join(reply.responding_to)}")
        print(f"  {reply.response}\n")
    else:
        print(f"\n  {reply.take}\n")
    moves = (turn.changes or {}).get("ratings", {})
    for name, rating in reply.ratings:
        move = moves.get(name)
        was = f"  (was {move['from']})" if move and move["from"] != move["to"] else ""
        print(f"    {name:<22} {rating.score:>2}/10  {rating.reason}{was}")
    lean = f"lean: {reply.lean.upper()}"
    if turn.changes and turn.changes["changed_mind"]:
        lean += f" (changed from {turn.changes['lean']['from'].upper()})"
    print(f"\n    {lean}   confidence: {reply.confidence}/10   ({turn.seconds:.0f}s)")


def on_event(event):
    """Called by the orchestrator as things happen, so the screen keeps up with the debate."""
    kind = event["event"]
    if kind == "intake_done":
        found = f"a gadget, category {event['category']}" if event["is_tech_gadget"] else "not a gadget"
        failed = " (the check failed, so the council assumes a gadget)" if not event["ok"] else ""
        print(f"Intake check: {found}{failed}. {event['note']}  ({event['seconds']:.0f}s)")
    elif kind == "round_start":
        print(f"\n---------------- Round {event['round']}: {event['kind']} ----------------")
    elif kind == "agent_start":
        print(f"\n{event['agent']}")
    elif kind == "tool_call":
        print(f"    tool: {event['tool']}({json.dumps(event['arguments'])})")
        print(f"          -> {event['summary'] if event['ok'] else 'REJECTED: ' + event['summary'][:150]}")
    elif kind == "agent_done":
        turn = event["turn"]
        show_attempts(turn.trace)
        if turn.status == "ok":
            show_reply(turn)
        else:
            print(f"  {turn.agent} did not answer this round and sits out the rest of the debate.")
    elif kind == "round_done":
        print(f"\nRound {event['round']} done in {event['seconds']:.0f}s")
    elif kind == "scored":
        print(f"\nScoring (code): {event['score']} out of 10 -> {event['verdict_label']}")
    elif kind == "verdict":
        source = "template fallback" if event["fallback_used"] else "the Judge"
        print(f"Ruling written by {source} ({event['seconds']:.0f}s)")


def largest_prompt(session) -> int:
    sizes = [
        call.get("prompt_tokens") or 0
        for round_ in session["rounds"] for turn in round_["turns"]
        for call in [*turn["trace"].get("model_calls", []), *turn["trace"].get("attempts", [])]
    ]
    sizes += [a.get("prompt_tokens") or 0 for a in session["judge"]["trace"]["attempts"]]
    return max(sizes, default=0)


def verdict_card(session):
    scoring, ruling = session["scoring"], session["judge"]
    print("\n" + "*" * 72)
    print(f"  VERDICT: {scoring['verdict_label'].upper()}   ({scoring['score']} out of 10)")
    print(f"  {ruling['ruling']}")
    print("*" * 72)
    if scoring.get("rail_note"):
        print(f"\n  {scoring['rail_note']}")
    print(f"\n  How it went: {ruling['summary']}")
    print(f"  Strongest for:     {ruling['strongest_for']['agent']}: {ruling['strongest_for']['point']}")
    print(f"  Strongest against: {ruling['strongest_against']['agent']}: {ruling['strongest_against']['point']}")
    print(f"  Most persuasive:   {ruling['most_persuasive']}")
    print(f"  Would change it:   {ruling['would_change_verdict']}")
    for attempt in ruling["trace"]["attempts"]:
        if not attempt["ok"]:
            print(f"  (Judge attempt {attempt['attempt']} rejected: {attempt['error']})")

    timing = session["timing"]
    rounds = ", ".join(f"round {r['number']} {r['seconds']:.0f}s" for r in timing["per_round"])
    print(f"\n  Agent averages: " + ", ".join(f"{a} {v}" for a, v in scoring["agent_averages"].items()))
    print(f"  Time: {timing['total_seconds']:.0f}s in all (intake {timing['intake_seconds']:.0f}s, {rounds}, "
          f"Judge {timing['judge_seconds']:.0f}s)")
    print(f"  Largest prompt: {largest_prompt(session)} tokens (window is {config.CONTEXT_TOKENS})")
