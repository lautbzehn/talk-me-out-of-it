# 0003 · Tools are exact Python; the model only picks the inputs

**Status:** Accepted · **v1.0 · 10.29.2026**

## Context
A 7B model asked for cost per use did the division wrong, and when it could type a resale value it invented one. The brief wanted at least two real tools and no fabricated prices.

## Decision
Two pure functions, `cost_per_use` and `estimate_resale`. The model estimates the assumptions (uses a week, years kept, the category) and code does every calculation, including the resale lookup, so there is no input through which a dollar amount can be typed. Inputs forbid unknown fields; a made-up argument is an error that names the real fields. Tool steps run at temperature 0. Code, not the model, decides when the tool phase is done, and identical repeated calls are not run again.

## Consequences
- The arithmetic in every debate is exact and the assumptions are on the record in the trace, where they can be audited.
- A prompt change can change the model's assumptions (the commute went from 10 uses a week to 5 after one rewrite), so tool inputs are compared before and after any prompt edit.
- Resale is a rough category lookup and is labeled unverified everywhere it appears.
