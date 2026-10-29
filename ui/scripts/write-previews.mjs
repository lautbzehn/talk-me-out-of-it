// Runs after `vite build` (npm's "postbuild"). Writes one small HTML page per gallery session at
// dist/s/<id>.html, and adds the link-preview tags to dist/index.html.
//
// The file is s/<id>.html, not s/<id>/index.html, because the app's links have no trailing slash
// (/s/<id>). Static hosts, Cloudflare among them, serve s/<id>.html at /s/<id>; a folder
// index would only answer /s/<id>/ on some of them.
//
// Why: when someone pastes a link into a chat or a social post, the site that shows the preview
// fetches the page and reads its <head>. It does not run JavaScript, so the app cannot set the
// title, description and image. Every address has to ship with its own tags already in the HTML.
// Each session page is a copy of the built index.html (same script and styles, so the app still
// opens as usual) with that session's tags swapped in.
//
// The preview images are ui/public/previews/<id>.png, made once with the export tool
// (npm run dev, then open /export.html) and committed. A session without one falls back to the
// home image and prints a warning.
//
// No package: Node reads the shared page text straight from src/lib/page-text.ts, which it can run
// by stripping the type annotations (Node 22.18 or later).
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dist = resolve(here, "..", "dist");

// The address the site is served from, with no trailing slash. Preview tags need absolute URLs.
// The default is this project's own subdomain, like navigator.icarianforge.com for the Navigator.
// Set SITE_URL in the build environment to override it, e.g. `SITE_URL=https://example.test npm run build`.
const DEFAULT_SITE_URL = "https://talk.icarianforge.com";
const siteUrl = (process.env.SITE_URL || DEFAULT_SITE_URL).replace(/\/+$/, "");

let text;
try {
  text = await import("../src/lib/page-text.ts");
} catch (error) {
  console.error(
    `write-previews: cannot load src/lib/page-text.ts (${error.message}). ` +
      `Node ${process.version} may be too old to run TypeScript files; use Node 22.18 or later.`,
  );
  process.exit(1);
}

function fail(message) {
  console.error(`write-previews: ${message}`);
  process.exit(1);
}

const templatePath = join(dist, "index.html");
const indexPath = join(dist, "gallery", "index.json");
if (!existsSync(templatePath)) fail(`${templatePath} is missing; run the build first`);
if (!existsSync(indexPath)) fail(`${indexPath} is missing; run the build first`);

const template = readFileSync(templatePath, "utf8");
// Running twice on the same dist would stack the tags. The build starts from an empty dist every time.
if (template.includes('property="og:')) fail("dist/index.html already has preview tags; run the build again for a fresh dist");
const index = JSON.parse(readFileSync(indexPath, "utf8"));
if (!Array.isArray(index.sessions)) fail("gallery/index.json has no sessions list");

const escapeHtml = (s) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

// The two lines of index.html that every page changes. If someone edits index.html so that these
// stop matching, fail loudly instead of shipping previews with the wrong words.
const TITLE = /<title>[^<]*<\/title>/;
const DESCRIPTION = /<meta name="description" content="[^"]*"\s*\/?>/;
if (!TITLE.test(template) || !DESCRIPTION.test(template)) {
  fail('index.html must keep its <title> and <meta name="description" ...> lines in this exact shape');
}
const homeTitle = /<title>([^<]*)<\/title>/.exec(template)[1];
const homeDescription = /<meta name="description" content="([^"]*)"/.exec(template)[1];

const hasImage = (name) => existsSync(join(dist, "previews", `${name}.png`));
if (!hasImage("home")) console.warn("write-previews: warning: no previews/home.png; the home page has no preview image");

function page({ title, description, path, image, imageAlt }) {
  const url = `${siteUrl}${path}`;
  const t = escapeHtml(title);
  const d = escapeHtml(description);
  const tags = [
    `<meta name="description" content="${d}" />`,
    `<link rel="canonical" href="${escapeHtml(url)}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:site_name" content="${escapeHtml(text.SITE_TITLE)}" />`,
    `<meta property="og:title" content="${t}" />`,
    `<meta property="og:description" content="${d}" />`,
    `<meta property="og:url" content="${escapeHtml(url)}" />`,
  ];
  if (image) {
    const src = escapeHtml(`${siteUrl}/previews/${image}.png`);
    tags.push(
      `<meta property="og:image" content="${src}" />`,
      `<meta property="og:image:width" content="1200" />`,
      `<meta property="og:image:height" content="630" />`,
      `<meta property="og:image:alt" content="${escapeHtml(imageAlt)}" />`,
      `<meta name="twitter:card" content="summary_large_image" />`,
      `<meta name="twitter:title" content="${t}" />`,
      `<meta name="twitter:description" content="${d}" />`,
      `<meta name="twitter:image" content="${src}" />`,
      `<meta name="twitter:image:alt" content="${escapeHtml(imageAlt)}" />`,
    );
  } else {
    tags.push(`<meta name="twitter:card" content="summary" />`);
  }
  // Function replacements, so "$" in a title or description is never read as a replacement pattern.
  return template
    .replace(TITLE, () => `<title>${t}</title>`)
    .replace(DESCRIPTION, () => tags.join("\n    "));
}

// Home.
writeFileSync(
  templatePath,
  page({
    title: homeTitle,
    description: homeDescription,
    path: "/",
    image: hasImage("home") ? "home" : null,
    imageAlt: `${text.SITE_TITLE}: a council of AI agents argues about the gadget you want, then rules Buy, Wait 30 days, or Skip.`,
  }),
);

// One page per session.
const SAFE_ID = /^[A-Za-z0-9._-]+$/;
let written = 0;
let withoutImage = 0;
for (const session of index.sessions) {
  if (typeof session.id !== "string" || !SAFE_ID.test(session.id) || session.id.startsWith(".")) {
    fail(`session id ${JSON.stringify(session.id)} is not a safe file name`);
  }
  const own = hasImage(session.id);
  if (!own) {
    withoutImage += 1;
    console.warn(`write-previews: warning: no previews/${session.id}.png; using the home image for this session`);
  }
  mkdirSync(join(dist, "s"), { recursive: true });
  writeFileSync(
    join(dist, "s", `${session.id}.html`),
    page({
      title: text.pageTitle(session),
      description: text.pageDescription(session),
      path: `/s/${session.id}`,
      image: own ? session.id : hasImage("home") ? "home" : null,
      imageAlt: own ? text.imageAlt(session) : `${text.SITE_TITLE}: a council of AI agents argues about the gadget you want.`,
    }),
  );
  written += 1;
}

console.log(
  `write-previews: wrote ${written} session pages and the home tags for ${siteUrl}` +
    (withoutImage > 0 ? ` (${withoutImage} without their own image)` : ""),
);
