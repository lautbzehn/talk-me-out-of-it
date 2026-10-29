# 0007 · The site only reads transcripts, and a transcript explains itself

**Status:** Accepted · **v1.0 · 10.29.2026**

## Context
The brief kept the engine and the site apart, and wanted "Under the hood" to show the agent order, rounds, tool calls, ratings, scoring math and run time. Live mode was ruled out (a hosted model costs money), so everything a visitor sees had to come from saved runs.

## Decision
The engine writes one JSON file per session and the site reads JSON and nothing else; a build step copies `sessions/gallery/` into the site, so there is no hand-edited copy. Each council session carries an `engine` block: every member's focus, voice, rubric, tools and full system prompt, the tool descriptions, the intake, Judge and rebuttal prompts, and the scoring rules. A session is checked on write and on read, and the story check recomputes the score from its own ratings. Per-turn messages are not saved, since the prompts and the rounds already hold what rebuilds them.

## Consequences
- What the page shows is exactly what the council produced, and a reader can verify the arithmetic on the page or in `session_schema.py`.
- A session saved today still says what engine produced it after the prompts and cut-offs change, which the build log needed more than once.
- A transcript is about 45 KB, 20 KB of it the engine block; the gallery of eight is 420 KB and loads one file per chosen session.
- The site has two parsers: a strict one for the debate, which refuses a file it cannot play, and a lenient one for the trace panel, which hides a detail rather than breaking the page.
