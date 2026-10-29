# 0006 · Scoring v2: equal weights, two cut-offs, two lean rails

**Status:** Accepted · **v1.0 · 10.29.2026** (designed and approved 10.28.2026)

## Context
Scoring v1 (a plain average with cut-offs at 6.5 and 4.5) was written before any run. On the 14B, which rates about two points lower than the 7B, it reached Buy in 4 of 30 expected Buys, and in 9 of 79 saved councils it landed on a verdict that no member had argued for.

## Decision
Designed on all 79 saved 14B councils with no model calls (`evals/design_v2.py`). The score is the plain average of each member's final ratings, with `cost_of_waiting` at weight 0 (about 2 for everything, so no signal). 5.5 and up is Buy, below 4.5 is Skip, between is Wait 30 days: a round pair on the plateau of good cut-offs, chosen because a one-point Wait band around the middle is easy to explain. Then two rails: Buy needs at least one member leaning Buy, Skip needs at least one leaning Skip; otherwise the verdict holds at Wait, and the result records which rail held it. Weights per item were tried and add nothing (69 of 79 either way), so they stay equal. The rails read final leans, not leans from any round, a choice Dan made after seeing both.

## Consequences
- 68 of 79 saved councils agree (v1: 42), 65 when the cut-offs are refitted leaving each purchase out; 0 verdicts nobody argued for, checked by a test on 300 random councils.
- The known cost: members drift toward Wait in the rebuttal, and the Buy rail then holds a right Buy at Wait (4 of 10 Buys in the first live run). That is a prompt question, left open, not a scoring one.
- The scale is the 14B's. Another model needs its cut-offs rechecked; the 7B never leans Skip, so its Skip rail could never open.
