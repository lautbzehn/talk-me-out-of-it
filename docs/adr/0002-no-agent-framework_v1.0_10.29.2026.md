# 0002 · No agent framework: a hand-written orchestrator

**Status:** Accepted · **v1.0 · 10.29.2026**

## Context
This is a learning project and a showcase. A framework would hide the parts worth learning (turn-taking, tool loops, retries, state between rounds) and make the result a wrapper around someone else's loop. The only dependencies allowed were the Ollama client and Pydantic.

## Decision
Write the orchestration in plain Python: `council.py` runs rounds and the tiebreak and stops; `agents/tool_loop.py` runs the request-run-reply loop; `agents/base.py` does structured output with retry; `debate.py` holds the shared state and renders the digest each member reads. Each file is small enough to read in one sitting and is tested against a fake model.

## Consequences
- Every failure seen in a real run could be fixed where it happened, in a function with a test, rather than worked around in a prompt.
- Agents run one after another, which is what one local model can do anyway; parallelism was never needed.
- Some conveniences a framework gives for free (conversation memory, tool specs from signatures) are written here by hand, each in a few dozen lines.
