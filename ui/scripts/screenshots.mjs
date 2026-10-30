// Takes the README screenshots from a running copy of the site, at 2x, with the Chrome already on
// this Mac. No package: Node's built-in WebSocket talks to Chrome's debugging protocol.
//
//   npm run preview --prefix ui            (or any server with the built site)
//   node ui/scripts/screenshots.mjs http://localhost:4173
//   node ui/scripts/screenshots.mjs https://talk.icarianforge.com      (the live site works too)
//
// Writes PNGs into docs/screenshots/. Each shot names a page, a viewport, what to do on the page
// first, and the box to capture (page coordinates, in CSS pixels). Reduced motion is emulated so
// the debate and the trace show finished rather than mid-animation.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9222;
const base = (process.argv[2] ?? "http://localhost:4173").replace(/\/+$/, "");
const out = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screenshots");
mkdirSync(out, { recursive: true });

const SESSION = "20261029-043202-noise-cancelling-headphones";
const PHONE_SESSION = "20261029-055348-sequel-to-my-favorite-video-game";

// `prepare` runs in the page and returns the {x, y, width, height} box to capture.
const SHOTS = [
  {
    name: "home",
    path: "/",
    viewport: { width: 1600, height: 1000, mobile: false },
    prepare: `({ x: 0, y: 0, width: 1600, height: 1000 })`,
  },
  {
    // The whole How it works section: 1024 px wide, as tall as it is. It has 24px of padding above
    // and 80px below, so cutting 56px from the height leaves an even 24px all round.
    name: "how-it-works",
    path: "/",
    viewport: { width: 1600, height: 1000, mobile: false },
    prepare: `(async () => {
      const el = document.querySelector('#how-it-works');
      el.scrollIntoView();
      await new Promise((r) => setTimeout(r, 800));
      const r = el.getBoundingClientRect();
      return { x: 288, y: r.top + window.scrollY, width: 1024, height: Math.ceil(r.height) - 56 };
    })()`,
  },
  {
    // The debate and Under the hood's run trace, side by side as they play. The session section is
    // 1152 px wide at this size (max-w-6xl), so x 224 is its left edge.
    name: "debate",
    path: `/s/${SESSION}`,
    viewport: { width: 1600, height: 1000, mobile: false },
    prepare: `(() => {
      const r = document.querySelector('#debate-title').closest('section').getBoundingClientRect();
      const top = r.top + window.scrollY - 24;
      return { x: 224, y: top, width: 1152, height: 1000 };
    })()`,
  },
  {
    // The rest of Under the hood, below them: the scoring math, the run in numbers, the brief.
    name: "under-the-hood",
    path: `/s/${SESSION}`,
    viewport: { width: 1600, height: 1000, mobile: false },
    prepare: `(async () => {
      await new Promise((r) => setTimeout(r, 1000));
      const r = document.querySelector('section[aria-labelledby=hood-more-name]').getBoundingClientRect();
      const top = r.top + window.scrollY - 24;
      return { x: 224, y: top, width: 1152, height: 1000 };
    })()`,
  },
  {
    name: "phone",
    path: `/s/${PHONE_SESSION}`,
    viewport: { width: 390, height: 844, mobile: true },
    prepare: `(() => {
      const r = document.querySelector('#session').getBoundingClientRect();
      return { x: 0, y: r.top + window.scrollY - 16, width: 390, height: 844 };
    })()`,
  },
];

const profile = mkdtempSync(join(tmpdir(), "tmooi-shots-"));
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  "--no-first-run",
  "--hide-scrollbars",
  "--window-size=1600,1000",
  "about:blank",
], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForChrome() {
  for (let i = 0; i < 50; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      if (res.ok) return;
    } catch {}
    await sleep(100);
  }
  throw new Error("Chrome's debugging port did not open");
}

/** One page, one WebSocket. Commands get an id; replies and events come back on the same socket. */
async function openPage() {
  const res = await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" });
  const { webSocketDebuggerUrl } = await res.json();
  const ws = new WebSocket(webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 1;
  const pending = new Map();
  const listeners = new Set();
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    } else if (msg.method) {
      for (const fn of listeners) fn(msg);
    }
  };
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  const once = (method) => new Promise((resolve) => {
    const fn = (msg) => { if (msg.method === method) { listeners.delete(fn); resolve(msg.params); } };
    listeners.add(fn);
  });
  return { send, once, close: () => ws.close() };
}

async function shoot(page, shot) {
  await page.send("Page.enable");
  await page.send("Emulation.setDeviceMetricsOverride", { ...shot.viewport, deviceScaleFactor: 2 });
  await page.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  const loaded = page.once("Page.loadEventFired");
  await page.send("Page.navigate", { url: `${base}${shot.path}` });
  await loaded;
  await sleep(1500); // the gallery index and the transcript are fetched after load
  const { result } = await page.send("Runtime.evaluate", { expression: shot.prepare, awaitPromise: true, returnByValue: true });
  const clip = { ...result.value, scale: 1 };
  const { data } = await page.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip });
  const file = join(out, `${shot.name}.png`);
  writeFileSync(file, Buffer.from(data, "base64"));
  console.log(`screenshots: wrote ${shot.name}.png (${clip.width * 2} by ${clip.height * 2})`);
}

try {
  await waitForChrome();
  for (const shot of SHOTS) {
    const page = await openPage();
    try {
      await shoot(page, shot);
    } finally {
      page.close();
    }
  }
} finally {
  // Wait for Chrome to exit before removing its profile, or the folder is still being written to.
  const exited = new Promise((r) => chrome.once("exit", r));
  chrome.kill();
  await exited;
  rmSync(profile, { recursive: true, force: true });
}
