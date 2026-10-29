"""Shared state: the debate so far, and how each agent gets to read it.

The orchestrator keeps one Debate. It holds rounds, and each round holds one turn per
agent. Agents never see this object or each other's raw JSON. Before an agent's turn,
code renders the others' turns into a short text digest, leaving out the reader's own
turn (it already has that in its own conversation).

"Changed its mind" is never asked of the model. compute_changes works it out from the
numbers, so the UI and the Judge can trust it.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel

from agents.schemas import AgentRebuttal, Purchase


@dataclass
class Turn:
    """One agent's turn in one round."""

    agent: str
    status: str  # "ok", or "failed" when it gave no valid answer (it then sits out the rest)
    reply: BaseModel | None  # an AgentTake in the opening round, an AgentRebuttal after; None if failed
    trace: dict
    seconds: float = 0.0
    changes: dict | None = None  # rebuttal rounds only: what moved since this agent's last reply
    conversation: list[dict] = field(default_factory=list, repr=False)  # the agent's own messages, for its next turn


@dataclass
class Round:
    number: int
    kind: str  # "opening", "rebuttal", or "tiebreak"
    turns: list[Turn] = field(default_factory=list)
    seconds: float = 0.0

    def answered(self) -> list[Turn]:
        return [turn for turn in self.turns if turn.status == "ok"]


@dataclass
class Debate:
    purchase: Purchase
    rounds: list[Round] = field(default_factory=list)
    category: str | None = None  # from the intake check; every agent's prompt includes it


def final_replies(debate: Debate) -> dict[str, BaseModel]:
    """Each agent's last valid reply, in speaking order. An agent that failed a later round
    keeps its last good one; an agent that never answered is not included."""
    final = {}
    for round_ in debate.rounds:
        for turn in round_.answered():
            final[turn.agent] = turn.reply
    return final


def compute_changes(before: BaseModel, after: BaseModel) -> dict:
    """Every rating, the lean and the confidence, old to new, worked out by code.
    `before` and `after` are any two replies from the same agent (take or rebuttal)."""
    ratings = {
        name: {"from": old.score, "to": getattr(after.ratings, name).score}
        for name, old in before.ratings
    }
    return {
        "ratings": ratings,
        "lean": {"from": before.lean, "to": after.lean},
        "confidence": {"from": before.confidence, "to": after.confidence},
        "changed_mind": before.lean != after.lean,
        "scores_moved": sum(1 for move in ratings.values() if move["from"] != move["to"]),
    }


def render_turn(turn: Turn) -> str:
    """One agent's turn as the others read it. Example:

    The Analyst leaned WAIT (confidence 7): "<take>"
      value_per_use 4: <reason>
      Tool result: Net cost $412.00 after ..."""
    if turn.status != "ok":
        return f"({turn.agent} did not answer this round.)"

    reply = turn.reply
    changes = turn.changes or {}
    if isinstance(reply, AgentRebuttal):
        lean = changes.get("lean", {})
        was = f", was {lean['from'].upper()}" if lean and lean["from"] != lean["to"] else ""
        header = (
            f"{turn.agent}, answering {' and '.join(reply.responding_to)}, now leans "
            f'{reply.lean.upper()} (confidence {reply.confidence}{was}): "{reply.response}"'
        )
    else:
        header = f'{turn.agent} leaned {reply.lean.upper()} (confidence {reply.confidence}): "{reply.take}"'

    lines = [header]
    for name, rating in reply.ratings:
        move = changes.get("ratings", {}).get(name)
        was = f" (was {move['from']})" if move and move["from"] != move["to"] else ""
        lines.append(f"  {name} {rating.score}{was}: {rating.reason}")
    for call in turn.trace.get("tool_calls", []):
        if call["ok"] and not call["duplicate"]:
            lines.append(f"  Tool result: {call['result']['summary']}")
    return "\n".join(lines)


def render_round(round_: Round, exclude: str | None = None) -> str:
    """A whole round as text, leaving out the `exclude` agent's own turn."""
    entries = [render_turn(turn) for turn in round_.turns if turn.agent != exclude]
    return f"Round {round_.number} ({round_.kind}):\n\n" + "\n\n".join(entries)


def render_debate(debate: Debate) -> str:
    """Every round, nobody left out. This is what the Judge reads."""
    return "\n\n".join(render_round(round_) for round_ in debate.rounds)
