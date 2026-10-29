"""Scoring: the model judges, the code calculates.

Agents return ratings and a lean (buy, wait or skip). This file turns them into one score and a
verdict. The model never sees or writes the final number, and the same ratings always give the
same result.

Version 2 (Phase 5, step 4). The design and the numbers behind it are in PROGRESS.md and
docs/build-log.md, and `python -m evals.design_v2` reproduces them from the saved eval runs.
1. The score is the plain average of every rating in each member's final turn, except
   cost_of_waiting, which has weight 0: the 14B rates it about 2 whatever the purchase, so it
   carries no signal. It is still rated and still shown; it just does not count.
2. 5.5 and up is Buy, below 4.5 is Skip, anything between is Wait 30 days. These sit on the
   plateau of good cut-offs on the 14B model's scale, and a one-point Wait band around the
   middle is easy to explain. They are not fitted to the last decimal.
3. Two lean rails, because ratings alone could land on a verdict that no member argued for
   (9 of 79 saved 14B councils under v1). Buy needs at least one member leaning Buy, and Skip
   needs at least one member leaning Skip. Otherwise the verdict steps to Wait 30 days. The
   score is not changed, and the result records which rail held the verdict so the card and
   the Judge can say so.

This is calibrated to qwen2.5:14b. Another model rates on another scale and needs its cut-offs
checked first (the 7B rates about 2 points higher, and never leans Skip).
"""

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel

FORMULA_VERSION = 2
BUY_AT = 5.5  # this score and above is Buy
WAIT_AT = 4.5  # this score up to BUY_AT is Wait 30 days; below it is Skip
VERDICT_LABELS = {"buy": "Buy", "wait": "Wait 30 days", "skip": "Skip"}

# Every rubric item and how much it counts. A new rubric item has no weight until someone decides
# one here: score() refuses to guess, and a test checks this list against the agents' rubrics.
WEIGHTS = {
    "value_per_use": 1,
    "longevity": 1,
    "upgrade_gap": 1,
    "six_month_glow": 1,
    "want_vs_reason": 1,
    "use_reality": 1,
    "price_for_the_problem": 1,
    "cost_of_waiting": 0,  # settled 10.24.2026, rechecked on the 14B: about 2 for everything
    "better_than_keeping_it": 1,
    "worth_full_price": 1,
    "release_timing": 1,
    "ecosystem_freedom": 1,
}

FORMULA = (
    "the average of every rating in each member's final turn, not counting cost of waiting; "
    "5.5 and above is Buy, below 4.5 is Skip, anything between is Wait 30 days; "
    "Buy needs at least one member leaning Buy and Skip needs at least one member leaning Skip, "
    "otherwise the verdict is Wait 30 days"
)

# What a rail says when it holds a verdict. Written by code, so the card never needs the model to explain it.
RAIL_NOTES = {
    "buy_needs_a_buy_lean": "The score alone points to Buy, but no member leaned Buy, so the verdict holds at Wait 30 days.",
    "skip_needs_a_skip_lean": "The score alone points to Skip, but no member leaned Skip, so the verdict holds at Wait 30 days.",
}


def verdict_for(value: float) -> str:
    """The verdict the score alone points to, before the rails."""
    if value >= BUY_AT:
        return "buy"
    return "wait" if value >= WAIT_AT else "skip"


def apply_rails(verdict: str, leans: list[str]) -> tuple[str, str | None]:
    """Returns the final verdict and the name of the rail that changed it (None when none did).
    Both rails only ever move a verdict to Wait, so no rail can turn Buy into Skip or back."""
    if verdict == "buy" and "buy" not in leans:
        return "wait", "buy_needs_a_buy_lean"
    if verdict == "skip" and "skip" not in leans:
        return "wait", "skip_needs_a_skip_lean"
    return verdict, None


def counted_ratings(inputs: dict[str, dict[str, int]]) -> dict[str, list[tuple[int, int]]]:
    """For each agent, its (score, weight) pairs that count. A rating with weight 0 is left out."""
    unknown = sorted({name for ratings in inputs.values() for name in ratings if name not in WEIGHTS})
    if unknown:
        raise ValueError(f"no scoring weight for {', '.join(unknown)}; add it to WEIGHTS in scoring.py")
    return {agent: [(value, WEIGHTS[name]) for name, value in ratings.items() if WEIGHTS[name] > 0]
            for agent, ratings in inputs.items()}


def average_of(inputs: dict[str, dict[str, int]]) -> float:
    """The council's score from `{agent: {rating name: score}}`, rounded to one decimal.

    This is the whole arithmetic of the score, apart from the verdict. It takes plain numbers, so a
    saved session can be checked later: the number on its card must be what its own ratings give.
    Rounding uses Decimal because Python's round() rounds halves to the nearest even digit
    (round(6.25, 1) gives 6.2), and people expect 6.3."""
    pairs = [pair for agent_pairs in counted_ratings(inputs).values() for pair in agent_pairs]
    total_weight = sum(weight for _, weight in pairs)
    if not total_weight:
        raise ValueError("there are no ratings to score")
    average = (sum(Decimal(value) * weight for value, weight in pairs) / Decimal(total_weight)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP)
    return float(average)


def score(final_replies: dict[str, BaseModel]) -> dict:
    """`final_replies` maps each agent's name to its last valid reply (a take or a rebuttal).

    The average is rounded to one decimal before the verdict is picked, so the number on the
    card always matches the score's own verdict."""
    inputs = {agent: {name: rating.score for name, rating in reply.ratings} for agent, reply in final_replies.items()}
    counted = counted_ratings(inputs)
    pairs = [pair for agent_pairs in counted.values() for pair in agent_pairs]
    value = average_of(inputs)
    leans = {agent: reply.lean for agent, reply in final_replies.items()}
    by_score = verdict_for(value)
    verdict, rail = apply_rails(by_score, list(leans.values()))
    return {
        "score": value,
        "verdict": verdict,
        "verdict_label": VERDICT_LABELS[verdict],
        "formula_version": FORMULA_VERSION,
        "formula": FORMULA,
        "inputs": inputs,
        "not_counted": sorted({name for ratings in inputs.values() for name in ratings if WEIGHTS[name] == 0}),
        "agent_averages": {
            agent: round(float(sum(Decimal(v) * w for v, w in agent_pairs) / sum(w for _, w in agent_pairs)), 2)
            for agent, agent_pairs in counted.items() if agent_pairs
        },
        "ratings_counted": len(pairs),
        "leans": leans,
        "score_verdict": by_score,
        "rail": rail,
        "rail_note": RAIL_NOTES.get(rail),
    }
