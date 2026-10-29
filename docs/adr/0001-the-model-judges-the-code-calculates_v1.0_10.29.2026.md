# 0001 · The model judges; the code calculates

**Status:** Accepted · **v1.0 · 10.29.2026**

## Context
A language model is good at weighing an argument and bad at arithmetic, consistency, and knowing when it is making a number up. A verdict that the model simply announced would be unverifiable, and a small local model would give a different one each run.

## Decision
Agents return structured ratings (1 to 10, one direction: 10 favors buying) and a lean. Python computes the score and the verdict (`scoring.py`). The Judge's schema has no verdict or score field; it explains a verdict it is given, and if it fails its checks, code writes a template ruling. Every number an agent writes must already appear in what it read.

## Consequences
- The same ratings always give the same verdict, and a saved session can be checked: the site recomputes the score from the ratings in the browser, and `session_schema.py` does it on write and read.
- The model's job shrinks to the part it is good at. Reliability on the 14B went to 2 to 5 rejected answers in 100 turns.
- The Judge sometimes misstates who leaned where when the verdict differs from the lean tally. Code writes the rail note the card shows, so the Judge's version is never the record.
