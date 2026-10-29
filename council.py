"""The orchestrator: a hand-written loop that runs the council from start to verdict.

run_council does this, in order:
1. Check the purchase (Pydantic) and run the intake check. Politely decline if it is not a gadget.
2. Round 1, opening: each agent gives its take in speaking order.
3. Round 2, rebuttal: each agent answers the others and scores again.
4. Tiebreak: while the council is split and the round cap allows, one more rebuttal round.
5. Scoring: code turns the final ratings into a score and a verdict.
6. The Judge explains that verdict. It cannot change it.
7. Return the whole session as a plain dict, ready to save as JSON.

Agents run one after another, never in parallel. The Mac runs one model, and each
round needs the whole previous round.
"""

import time
from collections import Counter
from datetime import datetime, timezone

import httpx

import config
import scoring
from agents import intake as intake_agent
from agents import judge
from agents.base import StructuredOutputError, default_chat
from agents.council_agent import REBUTTAL_PROMPT, open_turn, rebuttal_turn
from agents.guard import guard_purchase
from agents.intake import check_intake
from agents.roster import COUNCIL
from agents.schemas import Purchase
from debate import Debate, Round, Turn, compute_changes, final_replies, render_round
from tools.registry import TOOLS

# 2: the injection guard's record ("guard") and the intake's why_has_instructions
# 3: council sessions carry an "engine" snapshot (see engine_snapshot), so a transcript explains itself
SESSION_SCHEMA_VERSION = 3
# Written by code around the user's own item name. An earlier version spliced in the intake
# note, but the model wrote "Leather sofa" instead of a sentence and the message broke.
DECLINE_MESSAGE = (
    'The council only weighs in on tech gadgets, like consoles, headphones, phones, cameras and laptops, '
    'and "{item}" doesn\'t look like one. Try it with a gadget you\'re thinking about buying.'
)


class CouncilError(Exception):
    """The council cannot go on, for example because fewer than two agents are still answering."""


def emit(on_event, **event):
    """Tell the caller what just happened, if it asked to be told. `on_event` is a callback:
    a function the caller hands in, which the orchestrator calls with one dict per event."""
    if on_event:
        on_event(event)


def take_turn(current: Round, agent, run, on_event, previous_reply=None) -> Turn:
    """Run one agent's turn and time it. A failure becomes a "failed" turn instead of
    stopping the debate: the agent sits out, and the digest tells the others.
    With `previous_reply` (rebuttal rounds), code also works out what changed."""
    emit(on_event, event="agent_start", round=current.number, agent=agent.name)
    started = time.perf_counter()
    try:
        reply, trace, conversation = run()
        turn = Turn(agent.name, "ok", reply, trace, conversation=conversation)
    except StructuredOutputError as error:
        turn = Turn(agent.name, "failed", None, error.trace or {"attempts": error.attempts})
    except httpx.TimeoutException:
        error = f"a model call took longer than {config.REQUEST_TIMEOUT_SECONDS} seconds"
        turn = Turn(agent.name, "failed", None, {"tool_calls": [], "attempts": [], "error": error})
    turn.seconds = round(time.perf_counter() - started, 2)
    if turn.status == "ok" and previous_reply is not None:
        turn.changes = compute_changes(previous_reply, turn.reply)
    current.turns.append(turn)
    emit(on_event, event="agent_done", round=current.number, agent=agent.name,
         status=turn.status, seconds=turn.seconds, turn=turn)
    return turn


def start_round(debate: Debate, kind: str, on_event) -> Round:
    current = Round(number=len(debate.rounds) + 1, kind=kind)
    debate.rounds.append(current)
    emit(on_event, event="round_start", round=current.number, kind=kind)
    return current


def finish_round(current: Round, started: float, on_event) -> Round:
    current.seconds = round(time.perf_counter() - started, 2)
    emit(on_event, event="round_done", round=current.number, kind=current.kind, seconds=current.seconds)
    return current


def run_opening_round(debate: Debate, chat=default_chat, agents=COUNCIL, on_event=None) -> Round:
    """Round 1: every agent gives its take in speaking order, without seeing the others."""
    started = time.perf_counter()
    current = start_round(debate, "opening", on_event)
    for agent in agents:
        def report_tool(record, agent=agent):
            emit(on_event, event="tool_call", round=current.number, agent=agent.name, tool=record["tool"],
                 arguments=record["arguments"], ok=record["ok"],
                 summary=record["result"]["summary"] if record["ok"] else record["error"])

        take_turn(
            current, agent,
            lambda: open_turn(agent, debate.purchase, chat=chat, category=debate.category, on_tool_call=report_tool),
            on_event,
        )
    return finish_round(current, started, on_event)


def run_rebuttal_round(
    debate: Debate, kind="rebuttal", chat=default_chat, agents=COUNCIL, on_event=None, note: str = ""
) -> Round:
    """Every agent that answered last round reads the others' turns from that round,
    answers them, and scores its rubric again. `note` is passed to every agent.

    Everyone reads the same previous round, never the earlier speakers of this round,
    so speaking order gives no one the last word."""
    previous = debate.rounds[-1]
    last_turns = {turn.agent: turn for turn in previous.answered()}
    if len(last_turns) < 2:
        raise CouncilError(
            f"Only {len(last_turns)} agent(s) answered round {previous.number}. A rebuttal needs at least two."
        )

    started = time.perf_counter()
    current = start_round(debate, kind, on_event)
    for agent in agents:
        last = last_turns.get(agent.name)
        if last is None:
            continue  # it gave no answer last round, so it sits out the rest of the debate
        digest = render_round(previous, exclude=agent.name)
        speakers = [name for name in last_turns if name != agent.name]
        take_turn(
            current, agent,
            lambda: rebuttal_turn(agent, last.conversation, digest, speakers, chat=chat, note=note),
            on_event, previous_reply=last.reply,
        )
    return finish_round(current, started, on_event)


def lean_tally(leans: list[str]) -> str:
    """Example: "2 buy, 2 wait"."""
    return ", ".join(f"{count} {lean}" for lean, count in Counter(leans).most_common())


def is_split(leans: list[str]) -> bool:
    """Split means no lean is held by at least three of the agents still in the debate.
    With four agents, 2-2 and 2-1-1 are split; 3-1 and 4-0 are not. With fewer than three
    agents left, all of them must agree."""
    if not leans:
        return False
    return max(Counter(leans).values()) < min(3, len(leans))


def run_council(purchase, chat=default_chat, on_event=None, max_rounds: int = config.MAX_ROUNDS) -> dict:
    """Run the whole council on one purchase and return the session dict.
    `purchase` can be a Purchase or a plain dict with the same fields."""
    started = time.perf_counter()
    purchase = Purchase.model_validate(purchase)

    intake, intake_record = check_intake(purchase, chat=chat)
    # The agents read the purchase with any instructions in the "why" set aside; the session
    # keeps what the user typed, plus the guard's record of what was removed.
    read_as, guard = guard_purchase(purchase, flagged_by_intake=intake.why_has_instructions)
    emit(on_event, event="intake_done", is_tech_gadget=intake.is_tech_gadget, category=intake.category,
         ok=intake_record["ok"], note=intake.note, seconds=intake_record["seconds"],
         instructions_set_aside=guard["triggered"])
    intake_info = {**intake.model_dump(), **intake_record}
    if not intake.is_tech_gadget:
        return declined_session(purchase, intake_info, guard, started)

    debate = Debate(read_as, category=intake.category)
    run_opening_round(debate, chat=chat, on_event=on_event)
    if max_rounds >= 2:
        run_rebuttal_round(debate, chat=chat, on_event=on_event)
    while len(debate.rounds) < max_rounds:
        leans = [reply.lean for reply in final_replies(debate).values()]
        if not is_split(leans):
            break
        last_round = len(debate.rounds) + 1 == max_rounds
        note = f"The council is split ({lean_tally(leans)})." + (
            " This is the last round, so make your strongest case." if last_round else ""
        )
        run_rebuttal_round(debate, kind="tiebreak", chat=chat, on_event=on_event, note=note)

    final = final_replies(debate)
    if len(final) < 2:
        raise CouncilError(f"Only {len(final)} agent(s) gave a final answer. A verdict needs at least two.")
    result = scoring.score(final)
    emit(on_event, event="scored", score=result["score"], verdict=result["verdict"],
         verdict_label=result["verdict_label"])

    judge_started = time.perf_counter()
    ruling, judge_trace, fallback_used = judge.rule(debate, result, chat=chat)
    judge_seconds = round(time.perf_counter() - judge_started, 2)
    emit(on_event, event="verdict", verdict=result["verdict"], verdict_label=result["verdict_label"],
         score=result["score"], ruling=ruling.ruling, fallback_used=fallback_used, seconds=judge_seconds)

    return {
        **session_header("council", purchase, intake_info, guard),
        "engine": engine_snapshot(),
        "rounds": [round_record(round_) for round_ in debate.rounds],
        "scoring": result,
        "judge": {**ruling.model_dump(), "fallback_used": fallback_used, "seconds": judge_seconds,
                  "trace": judge_trace},
        "timing": {
            "total_seconds": round(time.perf_counter() - started, 2),
            "intake_seconds": intake_record["seconds"],
            "per_round": [{"number": r.number, "kind": r.kind, "seconds": r.seconds} for r in debate.rounds],
            "judge_seconds": judge_seconds,
        },
    }


# Turning the session into plain data. Phase 6 writes this dict to /sessions as JSON,
# and the UI only ever reads that file.

def session_header(kind: str, purchase: Purchase, intake_info: dict, guard: dict) -> dict:
    return {
        "schema_version": SESSION_SCHEMA_VERSION,
        "kind": kind,  # "council", or "declined" when the intake check says it is not a gadget
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": config.MODEL,
        "purchase": purchase.model_dump(),
        "intake": intake_info,
        "guard": guard,  # what the injection guard set aside; purchase above is what the user typed
    }


def engine_snapshot() -> dict:
    """What this engine was when the session ran: who the council members are, the prompts they were
    given, the tools, and the scoring rules. The UI only ever reads the transcript, so everything the
    "Under the hood" view shows has to be in the transcript. It is also a record: the roles, rubrics
    and cut-offs change as the project grows, and a session saved today should still say what produced it.

    The per-turn messages are not saved: each agent's opening system prompt and the purchase are here and in
    the session, and each rebuttal prompt is the template below with the digest of the last round, which the
    rounds already hold. Saving them again would double the file for nothing the reader cannot rebuild."""
    return {
        "agents": [
            {
                "name": agent.name,
                "focus": agent.focus,
                "voice": agent.voice,
                "rubric": {name: field.description for name, field in agent.ratings.model_fields.items()},
                "tools": list(agent.tool_names),
                "required_tools": list(agent.required_tools),
                "system_prompt": agent.system_prompt(),
            }
            for agent in COUNCIL
        ],
        "tools": {tool.name: tool.description for tool in TOOLS.values()},
        "prompts": {"intake": intake_agent.SYSTEM_PROMPT, "judge": judge.SYSTEM_PROMPT, "rebuttal": REBUTTAL_PROMPT},
        "rules": {
            "scoring": {
                "formula_version": scoring.FORMULA_VERSION,
                "formula": scoring.FORMULA,
                "buy_at": scoring.BUY_AT,
                "wait_at": scoring.WAIT_AT,
                "weights": dict(scoring.WEIGHTS),
            },
            "max_rounds": config.MAX_ROUNDS,
            "max_attempts": config.MAX_ATTEMPTS,
            "temperature": config.TEMPERATURE,
            "context_tokens": config.CONTEXT_TOKENS,
        },
    }


def declined_session(purchase: Purchase, intake_info: dict, guard: dict, started: float) -> dict:
    return {
        **session_header("declined", purchase, intake_info, guard),
        "message": DECLINE_MESSAGE.format(item=purchase.item),
        "rounds": [],
        "scoring": None,
        "judge": None,
        "timing": {"total_seconds": round(time.perf_counter() - started, 2),
                   "intake_seconds": intake_info["seconds"], "per_round": [], "judge_seconds": 0},
    }


def round_record(round_: Round) -> dict:
    return {
        "number": round_.number,
        "kind": round_.kind,
        "seconds": round_.seconds,
        "turns": [
            {
                "agent": turn.agent,
                "status": turn.status,
                "take_or_rebuttal": turn.reply.model_dump() if turn.reply else None,
                "changes": turn.changes,
                "seconds": turn.seconds,
                "trace": turn.trace,
            }
            for turn in round_.turns
        ],
    }
