# Phase 7 UI: stack proposal and 21st.dev shortlist
v1.3 · 10.29.2026

Status 10.29.2026: Dan chose hero A, debate chat A (with B's typing indicator and C's badge), verdict card B, avatars B, background A, Under the hood A, buttons B and gallery cards C, and said yes to the stack and to the theme comparison. The stack is installed in `ui/`, the components are pulled and reviewed (`ui/pulled/REVIEW.md`), the three themes are on `docs/phase7-theme-board.html`, and milestone 1 is built. Theme: Darkmatter, chosen 10.29.2026. Current state lives in PROGRESS.md; the text below is the proposal as it was decided on.

Nothing here was installed or pulled when this was written. This is the proposal CLAUDE.md asks for before any building, so Dan can choose.

How this was made: I searched 21st.dev (free, metadata only) for each piece the brief names. The first pass was written from descriptions. Then Dan asked for images, so I saved the 25 preview thumbnails once (about 7.7 MB, shrunk to about 1 MB) into a scratch folder outside the repo, looked at every one, and revised five recommendations (pieces 2, 3, 4, 7 and 8). They went into a private comparison board for choosing. The previews belong to their authors and are not stored in the project. Every link opens the component's live demo on 21st.dev. No component code has been retrieved and no hosted AI generation was used (it is off on this account and the credit balance is 0).

## Part 1. The stack

**Proposed: Vite + React + TypeScript + Tailwind CSS, with shadcn-style components, Motion for animation and Lucide for icons.** It builds to plain static files in `ui/dist/`, which is what Cloudflare Pages serves. Node 26.10 and npm 11.19 are already on the Mac.

Why this one:
- **21st.dev is built for it.** Its components are React, Tailwind and shadcn. On this stack they drop in with little change. On plain HTML they would have to be rewritten, which wastes the plan Dan pays for.
- **It stays simple.** There is no server, no database and no accounts. The app fetches `index.json` and the transcripts as static files and plays them back.
- **It is fast and small.** Vite builds quickly and ships only what is used. Motion is the one animation library, so there is no pile of overlapping ones.

Alternatives I considered and rejected:
- **Plain HTML, CSS and JavaScript.** Fewest moving parts, but the chat replay, the animated gauge and the trace view would be hand-rolled, and the 21st.dev components would not fit.
- **Next.js.** It can export static files, but its server features would go unused and it adds weight and build complexity.
- **Astro.** A good fit for static pages and the closest rival. I would pick it only if per-session link previews turn out to be hard (next paragraph).

One real design problem to plan for now: **link previews.** A shared link to one verdict needs its own title, description and image in the page head, and social sites do not run JavaScript. A single-page app serves the same head for every URL. The fix is a small build step that writes one tiny HTML page per gallery session with the right tags. That is Phase 8 work, but it is why the app should use one URL per session from the start.

### Packages (CLAUDE.md asks me to explain each before installing)

| Package | What it is | Why it is needed |
|---|---|---|
| vite, @vitejs/plugin-react | Build tool and dev server | Turns the source into static files |
| react, react-dom | The UI library | Components and state |
| typescript | Typed JavaScript | Catches mistakes against the transcript shape before the browser does |
| tailwindcss (with its Vite plugin) | Utility CSS | What 21st.dev components are styled with |
| motion | Animation library (the successor to Framer Motion) | Message arrivals, gauge, panel open and close |
| lucide-react | Icon set | Agent icons and small UI symbols |
| clsx, tailwind-merge, class-variance-authority | Tiny class-name helpers | Required by shadcn-style components |
| Radix primitives (only as a component needs them) | Accessible accordion, tooltip and similar | Keyboard and screen reader support for free |

Security notes: all of these are widely used, but npm packages are the usual supply-chain risk. The plan is to pin exact versions, commit `package-lock.json`, install with `npm ci`, run `npm audit` after installing, and use `--ignore-scripts` unless a package truly needs an install script. Every 21st.dev component gets read for network calls, tracking and odd scripts before it goes in, as CLAUDE.md requires.

## Part 2. The shortlist (2 to 3 options per piece)

Each piece has a recommendation, but the choice is Dan's.

### 1. Landing hero (explains the idea in five seconds)
- **A. [Illuminated Hero](https://21st.dev/@efferd/components/illuminated-hero)** by efferd. Glowing animated headline. The boldest and most "sexy" of the set.
- **B. [Hero Section with Animated Grid](https://21st.dev/@shadcnui-blocks/components/hero-07)** by shadcnui-blocks. Badge, headline, subtext, two buttons, animated grid behind. Quieter and lighter.
- **C. [Cinematic landing Hero](https://21st.dev/@jahed/components/cinematic-landing-hero)** by jahed. No description on the page, so judge it from the preview video.
- **Recommended: A**, with B as the safe fallback if A reads as too loud on a phone.

### 2. The debate as a group chat
- **A. [Chat Messages](https://21st.dev/@nexus-ui/components/chat-messages)** by nexus-ui. A whole animated conversation with bubbles arriving one by one and typing indicators. Closest to the replay in the brief.
- **B. [Message Bubble](https://21st.dev/@framecn/components/message-bubble) plus [Typing Indicator](https://21st.dev/@ddoemonn/components/typing-indicator).** Separate building blocks. The bubble has a rise-in animation. The typing indicator has bouncing dots and announces itself to screen readers.
- **C. [Chat Bubble Reactions](https://21st.dev/@bundui/components/bubble4)** by bundui. Bubbles with small badges on the edge. The idea fits us: the badge could show that agent's lean (Buy, Wait or Skip).
- **Recommended: A for the look** (dark window, gradient bubbles), the typing indicator from B and the edge badge from C. The transcript decides timing and order, so we reuse A's look but not its player.

### 3. Verdict card
- **A. [Financial Score Cards](https://21st.dev/@designali-in/components/financial-score-cards)** by designali-in. Animated half-circle gauge, strength badge, staggered entrance. A natural home for a score from 1 to 10.
- **B. [Tweenly Chart KPI](https://21st.dev/@mirukullacode/components/tweenly-chart-kpi)** by mirukullacode. Count-up headline, delta pill, sparkline and an optional goal bar. The goal bar could mark the Buy and Wait lines at 5.5 and 4.5.
- **C. [Radar Score Chart](https://21st.dev/@sean0205/components/c-chart-24)** by sean0205. A glowing radar of weighted measures. Better suited to the rubric view than the card itself.
- **Recommended: B.** It is dark, reads as the most modern of the three, and its goal bar can mark the Buy and Wait lines. A's light gauges with heavy shadows look dated beside a dark theme. C moves to the ratings view under the hood.

### 4. Agent avatars (distinct color, icon and voice per agent)
- **A. [Avatar](https://21st.dev/@appica-dev/components/avatar)** by appica-dev. Icon or initials fallback, a status badge, and grouping. The status badge could mean "typing".
- **B. [User Presence Avatar](https://21st.dev/@adrielzimbril/components/user-presence-avatar)** by adrielzimbril. Avatars glide between two clusters when their state changes. Idea for us: a "where the council stands" strip where each agent slides to the Buy, Wait or Skip group when its lean changes in the rebuttal.
- **C. [Avatar Group with Tooltip](https://21st.dev/@ozantekin/components/avatar-group-with-tooltip).** Hover effects and tooltips. Hover does not exist on a phone, so this is the weakest fit.
- **Recommended: B.** One gradient orb per agent gives each its own color, and the orb clusters could show Buy, Wait and Skip. A's human-looking faces do not suit AI agents, and C needs hover.

### 5. Animated background
- **A. [LiquidAurora](https://21st.dev/@dhileepkumargm/components/liquid-aurora).** CSS only, no extra library. Cheapest.
- **B. [AuroraBackground](https://21st.dev/@dhileepkumargm/components/aurora-background-1).** CSS gradients driven by Motion. A little richer.
- **C. [Aurora Flow](https://21st.dev/@ruixen.ui/components/aurora-flow).** WebGL through the OGL library. The most striking and the heaviest. It adds a package and works the phone's graphics chip.
- **Recommended: A.** The brief says performance and readability come first. Whatever we pick should freeze to a still image when the phone asks for reduced motion.

### 6. "Under the hood" panel
- **A. [Agent Trace](https://21st.dev/@n1m4mz/components/agent-trace)** by n1m4mz. A waterfall timeline of an agent run with a scrub bar. It handles nested calls, retries and errors, token counts and timings, with no chart library and keyboard support. It matches our traced sessions closely.
- **B. [Chain of Thought](https://21st.dev/@nexus-ui/components/chain-of-thought)** by nexus-ui. A collapsible step-by-step timeline with per-step status. Simplest and best on a narrow screen.
- **C. [AI Agent Pipeline](https://21st.dev/@monolythdev/components/ai-agent-pipeline)** by monolythdev. An animated diagram of a request flowing through an agent into tool calls. Its demo is a made-up email and CRM flow, so it would need the most adaptation.
- **Recommended: A**, with B as the simple fallback for a narrow screen, and the radar from piece 3 for the ratings. Use a fluid [Accordion](https://21st.dev/@micka_design/components/accordion) for the progressive-disclosure sections themselves.

### 7. Buttons
- **A. [Shimmer Button](https://21st.dev/@dillionverma/components/shimmer-button)** by dillionverma (Magic UI). Widely used, so the most proven.
- **B. [Klyv Shimmer Button](https://21st.dev/@klyv-ui/components/klyv-shimmer-button).** A sheen plus a light that follows the pointer, done with CSS variables instead of state.
- **C. [Glow Button](https://21st.dev/@waleedkibhen/components/glow-button)** by waleedkibhen. A glow, a glare on hover and a soft press animation.
- **Recommended: B.** It ships a dark-theme set (bright primary, white, dark and no-glow variants) with the lime recolored to ours. A is the proven fallback.

### 8. Gallery cards (picking one of the 8 sessions)
- **A. [Spotlight Card](https://21st.dev/@preetsuthar17/components/spotlight-card).** A soft light follows the pointer.
- **B. [Hover Reveal Cards](https://21st.dev/@lavikatiyar/components/cards).** The hovered or focused card stays sharp and its neighbors blur. Keyboard accessible.
- **C. [Feature Grid Spotlight Cards](https://21st.dev/@mohammadshehadeh/components/feature-08).** Six cards on hairline rails with corner marks and a pointer spotlight.
- **Recommended: C**, in a dark variant, with a tap state added because all three lean on hover. A hairline grid fits eight sessions better than B's photo-card blur, and our sessions have no photos.

### 9. Theme
21st.dev themes are free CSS tokens, but they have no preview images in search. Candidates by popularity: [Darkmatter](https://21st.dev/community/themes/darkmatter), [Violet Dark](https://21st.dev/community/themes/violet-dark-1789799839906) and [Slate Dark](https://21st.dev/community/themes/slate-dark-1789202367405). The agents carry their own colors on top, so the theme only has to supply calm neutrals and one accent. Recommended next step: fetch those three (free), render a swatch strip next to a sample bubble and card, and let Dan choose by eye.

## Part 3. What I need from Dan

1. Pick one option for each of pieces 1 to 8, or say "go with your recommendations".
2. Say yes or no to the stack in Part 1.
3. Say whether to fetch the three themes and compare them (free).

After that: set up the stack, review the chosen components' code for network calls and tracking, and build the first milestone, a verdict card that reads `index.json`.
