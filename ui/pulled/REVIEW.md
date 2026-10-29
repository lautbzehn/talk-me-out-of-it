# Pulled 21st.dev components: security review
v1.5 · 10.29.2026

Everything here was pulled through the 21st.dev MCP on 10.29.2026 and saved exactly as
received, so the review below could be checked against the files. Nothing in this folder is
imported by the app. When a piece is adapted it is rewritten into `src/components/` in our own
visual system. The TypeScript config does not include `pulled/`, so these files are never
type-checked or built.

**What is kept in git (10.29.2026):** only the three components with an MIT license (Tweenly
Chart KPI, Klyv Shimmer Button, Feature Grid Spotlight Cards), so their license notices travel
with the repository, plus this file. The seven components and three themes that arrived with
no license text were taken out of git before the code was made public: they are
ignored by `.gitignore` (so a copy put back is never committed by accident), and the table
below remains the record of what each was, who wrote it and what the review found. This
repository starts from a single clean commit, so the originals were never published here.
They stay in the git history of the private archive repository, which is why that archive
must never be made public (see PROGRESS.md, Phase 8). The files this review describes as
"saved verbatim" for those ten pieces are therefore no longer here.

## Method

1. Read every file by hand for network calls, tracking, remote scripts, cookies,
   storage, dynamic code (`eval`, `new Function`, `import()`), and `postMessage`.
2. Then grepped all files for the same patterns to catch anything the read missed:
   `fetch(`, `XMLHttpRequest`, `WebSocket`, `sendBeacon`, `<script`, `http://`,
   `https://`, `gtag`, `analytics`, `posthog`, `segment.`, `sentry`, `mixpanel`,
   `eval(`, `new Function`, `document.cookie`, `localStorage`, `sessionStorage`,
   `indexedDB`, `postMessage`, `import(`.
3. Listed what each component expects that was not delivered (helper files, CSS,
   packages), because a missing file is where a later "install" step could pull in
   code nobody reviewed.

## Result

**No component makes a network call, loads a remote script, sets a cookie, uses
browser storage, or runs dynamic code.** The grep found three kinds of hits, all harmless:

- `xmlns="http://www.w3.org/2000/svg"` in the Illuminated Hero: the SVG namespace
  string, not a request.
- Ten `https://avatars.spaceui.one/...` image URLs in the User Presence Avatar
  **demo** file (sample profile pictures). The component itself has no URLs. We will
  not use the demo, and our avatars are gradient orbs, so no image is ever fetched.
- The 21st.dev page URL in the comment at the top of each theme file.

All browser APIs used are local: `ResizeObserver`, `IntersectionObserver`,
`matchMedia`, `requestAnimationFrame`, pointer capture, `getBoundingClientRect`, and
`style.setProperty` on the element itself.

## Per component

| # | Piece | Component | Author · license | Network or tracking | Delivered complete? |
|---|---|---|---|---|---|
| 1 | Hero | Illuminated Hero | efferd · no license text | None | No: the `onloadbgt`, `onloadbgb`, `onloadopacity` keyframes and the `.shadow-bgt` / `.shadow-bgb` classes are not in the file. We write our own. |
| 2 | Debate look | Chat Messages | nexus-ui · no license text | None. Imports `framer-motion` (we use its successor `motion`; same API, one import path change). Contains Nexus branding text and a fake canned reply in demo mode, both local. | Yes |
| 2 | Typing dots | Typing Indicator | ddoemonn · no license text | None. Respects reduced motion, announces to screen readers. | Yes |
| 2 | Edge badge | Chat Bubble Reactions | bundui · no license text | None | Yes, needs `class-variance-authority` (not installed; we rewrite without it) |
| 3 | Verdict card | Tweenly Chart KPI | mirukullacode · MIT | None | No: imports `./tweenly-chart-kpi-utils/` (a chart kit with `ChartCard`, `ChartTooltip`, `createFormatter`, `linePath`, `useChartReveal`) and a `review-theme.css`, none delivered. We keep the ideas (count-up number, pill, goal bar) and write them ourselves. |
| 4 | Avatars | User Presence Avatar | adrielzimbril · no license text | None in the component; demo loads sample images from avatars.spaceui.one (not used) | No: needs `./user-presence-avatar-utils/tooltip` and `avatar-extended` (not delivered) and `@radix-ui/react-avatar`. The delivered `registry-avatar.tsx` is a plain Radix wrapper. We keep the cluster-and-glide idea and write orbs ourselves. |
| 5 | Background | LiquidAurora | dhileepkumargm · no license text | None | No: only the markup came; the `.liquid-shape` CSS and keyframes are missing. We write the CSS (three blurred blobs, CSS only). |
| 6 | Under the hood | Agent Trace | n1m4mz · no license text | None. Uses `IntersectionObserver` to pause off screen and `matchMedia` for reduced motion. | Yes, self-contained. Uses Tailwind v4 container queries. |
| 7 | Buttons | Klyv Shimmer Button | Klyv contributors · MIT | None | No: imports `./klyv-shimmer-button-utils/klyv-theme.css` (the `shimmer-sweep` keyframes, `--shadow-tile`, `--duration-slow`, the `accent`/`ink`/`surface` colors) which was not delivered. Small; we write it. |
| 8 | Gallery cards | Feature Grid Spotlight Cards | mohammadshehadeh · MIT | None | Yes, with the delivered `registry-badge.tsx`. Expects `--warm` and `--warm-glow` CSS variables, which we define. Needs `class-variance-authority` only for the badge (we drop it). |

"No license text" means the file carries none. 21st.dev publishes community components
for installation into projects, and the authors list them for that purpose. The three
MIT ones are explicit. If the site is ever sold or the code redistributed as a library,
check the licenses on each component's page first.

## Why the helper files are missing

The MCP's `get_component` returns the main file, the demo, and registry files, but not
the extra "utils" files some authors attach. The full set comes through the shadcn
install command, which needs a 21st.dev API key in an environment variable. The repo
holds no secrets, so that route was not used. The missing pieces are all small (a
keyframe, a few tokens, a card wrapper), and writing them ourselves fits the brief's
rule that every piece is adapted into one visual system anyway.

## What the app actually uses from each

Recorded as each milestone lands, so the diff between "pulled" and "ours" is clear:

- **Milestone 4 (Under the hood, 10.29.2026):** from Agent Trace, the run timeline: spans
  laid out under their parents, bars that fill to a playhead, the queued, running and done
  states (with the per-row screen-reader status), the ruler, the transport (play, a keyboard
  scrub slider, the clock), container-query columns, and the loop that writes one CSS variable
  per row per frame instead of re-rendering. Changed: our colors (a member's bar in its color, a
  rejected attempt striped since red means Skip here), member icons, short names on narrow
  screens, a fixed six-second replay, a details panel when a row is chosen; dropped the token
  counter, looping and the `cached` state. No code was copied line for line, and nothing was
  imported from `pulled/`: the file is `src/components/hood/RunTrace.tsx`. Chain of Thought, the
  narrow-screen fallback in the shortlist, was never pulled; Agent Trace works at phone width.
- **Milestone 3 (landing view, 10.29.2026):** from Illuminated Hero, the glowing headline:
  its eight-layer SVG filter rebuilt as one CSS `text-shadow` with the same warm colors; its
  `h-screen` layout, background shapes and missing load keyframes were not used. From
  LiquidAurora, the idea of three drifting blobs, with our own CSS (radial gradients and a
  transform-only keyframe, since its CSS never arrived). From Klyv Shimmer Button, the sheen
  sweep and the pointer light written to CSS custom properties, in Darkmatter's primary, as a
  link; its tones, sizes and theme file were not used. From Feature Grid Spotlight Cards, the
  card: hairline rails, crosshair corners, the warm corner glow (`--warm`, `--warm-glow`, now
  in `index.css`) and the pointer spotlight, plus a press state for phones; the demo's feature
  copy and the `Badge` (which needed `class-variance-authority`) were not used. No code was
  copied line for line, and nothing was imported from `pulled/`: the files are
  `src/components/Hero.tsx`, `Aurora.tsx`, `ShimmerButton.tsx` and `GalleryGrid.tsx`.
- **Milestone 2 (debate chat, 10.29.2026):** from Chat Messages, the look of a bubble
  (rounded corners with one squared corner by the avatar, a quiet border, the slide-and-settle
  entrance), re-colored per member with `--agent`; its scripted player, fake canned reply,
  input box and Nexus branding were not used. From Typing Indicator, the dots-in-a-bubble with
  an "X is typing" label and its screen-reader behavior (a separate polite status, announced
  after 700 ms); its presence hook and spring-driven wave were not used, the dots are one CSS
  keyframe. From Chat Bubble Reactions, the pill that straddles a bubble's bottom edge,
  rewritten without `class-variance-authority`. From User Presence Avatar, only the idea of
  an avatar chip, as gradient orbs with Lucide icons. No code was copied line for line, and
  nothing was imported from `pulled/`: the files are `src/components/debate/*` and
  `src/components/Debate.tsx`.
- **Milestone 1 (verdict card, 10.29.2026):** from Tweenly Chart KPI, the count-up
  headline (driven by `animate` from `motion`), the pill, and the goal bar turned into
  a 1-to-10 scale with the Wait and Buy lines at 4.5 and 5.5. The sparkline is left for
  the full-transcript view. No code was copied line for line; `src/components/VerdictCard.tsx`
  is written against our tokens.
