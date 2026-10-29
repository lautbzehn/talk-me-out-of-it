# 0004 · Validators are rules; prompts are suggestions

**Status:** Accepted · **v1.0 · 10.29.2026**

## Context
Every rule that was only in a prompt was broken by a real run: scores written into reasons, the want level repeated "out of 10", invented numbers, a rebuttal that named nobody, release timing stated as fact, Chinese characters mid-sentence, replies cut off at the length limit with the string closed cleanly.

## Decision
Anything that matters is a Pydantic validator on the reply schema, with a retry message that says exactly what broke and what to do ("335.83 instead of 335, or leave the number out"). The rubric descriptions live in the schema and are copied into the prompt, so the two cannot drift. Key names are treated as prompts too, since the model writes them into every answer, and a test rejects keys that would invite the wrong behavior.

## Consequences
- The 14B went from 0.07 rejected answers per turn to 0.02 after the rules were moved into code. A member that fails all three attempts sits out rather than stopping the debate; that happened once in the 23 gallery councils.
- Each validator costs a retry when it fires (about 20 to 50 seconds on the 14B), so rules are added only for failures actually seen.
- The list of rules and the failure behind each is kept in PROGRESS.md, so a new rule starts from what is known.
