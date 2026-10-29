# Security

## Reporting a vulnerability

Please email **hello@icarianforge.com** with "Security" in the subject line. Do not open a public issue. Include what you found, how to reproduce it, and what an attacker could do with it. I aim to reply within a few days and will credit you if you'd like.

**In scope:** this repository and `talk.icarianforge.com`.

## How the project is protected

| Area | Control |
|---|---|
| Secrets | None in the repository. The agents run on a local model, so there is no model API key to leak. Publishing uses the owner's own Cloudflare login on the owner's Mac; no deploy credentials are stored in GitHub. `.gitignore` excludes `.env`, keys, and local Cloudflare state. |
| The site | Static files only: no server code, no forms, no accounts, no database, no cookies, and nothing saved in the browser. The page loads only its own files (the fonts are self-hosted, and the only requests are for the site's own JSON transcripts) plus Cloudflare Web Analytics, which counts visits anonymously with no cookies and no identifiers, as on the other Icarian Forge sites. |
| Browser | A Content Security Policy that allows only the site's own scripts, styles, fonts and images and the Cloudflare Web Analytics beacon (`ui/public/_headers`), plus HSTS, `X-Content-Type-Options: nosniff`, `Cross-Origin-Opener-Policy: same-origin`, `strict-origin-when-cross-origin` referrers, no framing, no plugins, and camera, microphone, location, and payment access disabled. Checked against a local copy of Cloudflare's asset server: the whole site runs under the policy with no violations. |
| The council | Runs only on the owner's Mac. The public site replays saved transcripts and accepts no input, so visitors cannot send anything to a model. When the council does read a purchase, an injection guard sets aside instructions hidden in the "why" before any agent sees them, and no agent can buy anything or connect to a store. |
| Honest numbers | The model writes ratings and leans; code computes the score and the verdict. Every number an agent writes must appear in what it was given, and release timing is labeled unverified. A saved session is checked when it is written and again when it is read, so a gallery transcript cannot be hand-edited into a different verdict. |
| Supply chain | Dependabot watches npm, pip, and GitHub Actions. CI installs from the lockfile (`npm ci`) and from pinned `requirements.txt`, and GitHub Actions are pinned to a commit. The site's packages are pinned to exact versions, installed with install scripts off, and audited at each install. Third-party UI components were read for network calls, tracking, and dynamic code before any idea was adapted (`ui/pulled/REVIEW.md`). |
| Development tools | The export page and its save endpoint exist only while the dev server runs (`npm run dev`); they are not built or published. The endpoint takes only a PNG sent to a known name with a custom header. |

## Supported versions

Only the latest `main`, which is what the live site serves.
