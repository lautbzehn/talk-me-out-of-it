# Talk Me Out of It
Project brief · v1.3 · 10.29.2026

## What this is
A multi-agent "council" that debates whether someone should buy an expensive tech gadget
(video games, consoles, audio, video, computers, phones, cameras, wearables, smart home).
The user enters an item, the council argues it out, then delivers a verdict.

It has two goals:
1. The product: fun, instantly understandable for anyone, and marketable enough that
   people want to use it and share it.
2. The showcase: behind the scenes, it demonstrates real agent-building skill. Anyone
   technical who looks under the hood should see a well-built agent system, not a wrapper
   around one prompt.

## How to work with me
- I'm Dan. I'm new to Python and to building agents. This is a learning project, not just a build.
- Explain each new concept in plain language the first time it appears, then move on.
- Work in small milestones. At the end of each one, stop, show me what works, explain what I
  learned, and wait for my go-ahead before starting the next.
- Push back if I propose something that makes the result worse, slower, or more fragile.
- Writing style: plain, human language. Never use em dashes.

## Hard constraints
- Zero dollars. The agents run on a free local model through Ollama. Never add a paid API,
  API key, or paid service without asking me first.
- Runs on my personal Mac only.
- Never purchase anything or connect to a store account. This is a decision helper, not
  financial advice. Say so in the UI.
- The model judges, the code calculates. Agents return structured ratings; Python computes
  the final score and verdict. The model never invents the final number.
- Keep the agent engine and the UI separate. Python writes each session as a JSON transcript
  to /sessions. The UI only reads transcripts.
- The local model's product knowledge is out of date. Agents must not state current prices,
  release dates, or deals as facts. Use what the user provides, or label it "unverified".
  Agents should ask or advise checking rather than assert.
- Keep dependencies minimal. Before installing any third-party package, tell me what it is,
  why it's needed, and any security concern.
- No secrets in the repo. Set up .gitignore before the first commit.

## Language and stack
- Python for the whole agent engine: agents, orchestration, tools, scoring, evaluation,
  logging, and session export. This is the showcase, so it stays Python.
- Build the agent system from scratch. Do not use agent frameworks (LangChain, CrewAI,
  AutoGen and similar). Writing the orchestration loop myself is the point of the showcase.
- Expected Python dependencies: the official Ollama Python client and Pydantic for
  validating structured output. Anything beyond that needs my approval.
- The UI can use React, JavaScript or TypeScript, and modern UI libraries whenever they make
  the end product look and feel better. A build step (for example Vite) is fine.
- Choose the simplest UI stack that delivers a polished, fluid result, and explain the
  choice to me before setting it up. The final site must deploy as static files to
  Cloudflare Pages.

## The product
Inputs (keep it to these):
- Item name, price, why I want it, how badly I want it (1 to 10)
- Optional: the device I currently own that this would replace

The council (max five agents):
- The Analyst: cost per use, lifespan, what you're really paying for
- Future You: regret check, how this feels in six months
- Budget Guardian: opportunity cost, expressed in the user's own terms
- Alternatives Hunter: refurbished, last year's model, wait for a sale, cheaper option
- The Judge: reads the debate and rules

Gadget-specific factors the council should weigh:
- Upgrade gap versus the current device
- Release cycle risk (is a newer model likely soon?)
- Resale value and refurbished market
- Ecosystem lock-in

Flow:
1. Opening round: each agent gives a short take plus structured ratings
2. Rebuttal round: each agent responds to the others and may change its ratings
3. Scoring: Python combines the ratings into a confidence score
4. Verdict: Buy, Wait 30 days, or Skip, with a one-sentence reason

## Agent capabilities to demonstrate
Each of these should be real, working, and visible in "Under the hood" and the README:
- Orchestration: a hand-written loop that manages turns, rounds, and stopping
- Distinct agent roles: separate system prompts, voices, and rubrics per agent
- Structured output: Pydantic-validated JSON with automatic retry on malformed output
- Tool use: at least two deterministic Python tools agents can call, such as a cost-per-use
  calculator and a depreciation or resale estimator
- Shared state: agents read and respond to each other's arguments across rounds
- Guardrails: no fabricated prices, no purchase actions, graceful handling of off-topic input
- Tracing: every model call, tool call, rating, and timing logged into the session JSON
- Evaluation: a small test set of purchase scenarios with expected verdicts, plus a script
  that runs the council against them and reports how often it agrees

## Build phases
1. Setup: check my Mac's memory, choose an Ollama model that runs well on it, create a
   Python virtual environment, and make a first "hello" call to the model.
2. One agent that returns valid structured JSON, with retry if the output is malformed.
3. Tools: build the calculators and let one agent call them.
4. The full council plus rebuttal round, run by the orchestrator.
5. Scoring code, tests, and the evaluation script.
6. Save sessions as JSON with full traces. Curate 6 to 8 strong sessions for the gallery.
7. Replay UI (see below).
8. Marketability pass, then publish to icarianforge.com through GitHub and Cloudflare Pages.

## UI and UX direction (phase 7, not before)
- Sexy, sleek, modern, fluid. Dark theme. Mobile first.
- The debate plays out like a group chat: messages arrive one by one with typing indicators.
- Each agent has a distinct color, icon, and voice.
- Progressive disclosure: verdict card first, then the debate, then "Under the hood"
  (agent order, rounds, tool calls, ratings, scoring math, run time).
- Smooth motion and interactive elements, but performance and readability come first.
- Show version and date (vX.X · mm.dd.yyyy) in the UI footer.

Using 21st.dev:
- I have a monthly 21st.dev plan, so use it actively, not just for inspiration.
- Search, compare, and pull React components and themes for the key UI pieces: landing
  hero, chat bubbles and typing indicators, verdict card, agent avatars, animated
  backgrounds, buttons, and the "Under the hood" panel.
- Present 2 to 3 options for each major piece and let me choose before building it in.
- Adapt chosen components to one consistent visual system (colors, type, spacing, motion)
  so the result feels designed, not assembled.
- Check my plan usage before heavy retrieval. Hosted AI generation on 21st.dev may use
  separate credits, so ask me before using it.
- Review any component code pulled in for unexpected network calls, tracking, or
  suspicious scripts before adding it to the project.

## Marketability
- A clear name, a one-line hook, and a landing view that explains the idea in five seconds.
- Shareable verdict card: an image people can post, plus proper link previews.
- Gallery of real sessions so anyone can try the experience at zero cost to me.
- Fast load, accessible (contrast, keyboard, screen readers), works on any phone.
- A README that doubles as a case study: what it does, how the agent system works,
  an architecture diagram, key design decisions, and evaluation results.
- Live mode for visitors needs a hosted model and costs money. Plan for it, but don't
  build it until I decide it's worth it. If we do, it needs a spending cap and rate limits.

## Project standards
- Version every document and UI release as vX.X with mm.dd.yyyy. Keep a CHANGELOG.md.
- This file must stay named CLAUDE.md, so its version lives in the header above.
- Commit to git at the end of every milestone with a clear message. Public GitHub repo; the history from before publication is in a private archive repo.

## Folder structure
talk-me-out-of-it/
  CLAUDE.md
  CHANGELOG.md
  README.md
  agents/      agent definitions and prompts
  tools/       deterministic Python tools agents can call
  council.py   orchestrator
  scoring.py   deterministic scoring
  evals/       test scenarios and evaluation script
  sessions/    saved JSON transcripts with traces
  ui/          React replay app (built to static files for Cloudflare Pages)
  tests/

## Changes in v1.1 · 10.23.2026
- Python for all non-browser code, built from scratch with no agent frameworks
- Added the showcase goal and the list of agent capabilities to demonstrate
- Added tools and evaluation as their own build phases
- Added marketability requirements and the README case study
- Added 21st.dev as a design inspiration source

## Changes in v1.2 · 10.23.2026
- UI may use React, JavaScript or TypeScript, and a build step when it improves the product
- Agent engine stays pure Python, built from scratch
- 21st.dev moved from inspiration only to active use of components and themes
- Added a security review step for any pulled component code

## Changes in v1.3 · 10.29.2026
- The GitHub repo is public, starting from one clean commit; the earlier history is in the private archive repo
