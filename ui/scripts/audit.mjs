// Audits a running copy of the site: accessibility tree, text contrast, small screens, and load
// speed on a slow phone. It uses the Chrome already on this Mac, driven over its debugging protocol
// with Node's built-in WebSocket. No package.
//
//   node ui/scripts/audit.mjs https://talk.icarianforge.com
//   node ui/scripts/audit.mjs http://localhost:4173 --only=tree,perf --runs=3
//
// Checks (all by default; --only=a,b picks some):
//   tree      Chrome's own accessibility tree for the home page and for a session with Under the hood
//             open: landmarks, headings and every control, plus automatic flags (a control with no
//             name, a skipped heading level, no <main>, no page language). A flag is a prompt to
//             look, and "none" is not a screen reader test.
//   contrast  Every piece of visible text against the colors behind it (WCAG AA: 4.5 to 1, or 3 to 1
//             for large text). Text over a gradient or an image is measured against the plain color
//             under it and reported as "check by eye".
//   reflow    A 320 px wide screen (what 400% zoom gives): sideways scrolling, and controls smaller
//             than 24 by 24 px (WCAG 2.5.8). A card whose button is stretched over the whole card
//             counts as large.
//   perf      Chrome's "Slow 4G" (150 ms latency, 1.6 Mbps) with a 4x slower processor, on a phone
//             sized screen: first visits (no cache) and return visits (cache on), median of --runs
//             (default 5). Shows when the first paint, the largest paint and the gallery appear, how
//             much layout moved, and how many bytes and requests it took.
//
// Numbers from one Mac are a comparison between two builds, not what a visitor on a real phone
// will see. Run it on the live address before and after a change and compare.
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333; // not 9222, so it can run beside screenshots.mjs

const args = process.argv.slice(2);
const base = (args.find((a) => !a.startsWith("--")) ?? "").replace(/\/+$/, "");
if (!base) {
  console.error("Usage: node ui/scripts/audit.mjs <site address> [--only=tree,contrast,reflow,perf] [--runs=5]");
  process.exit(1);
}
const option = (name) => args.find((a) => a.startsWith(`--${name}=`))?.slice(name.length + 3);
const only = option("only")?.split(",");
const wants = (check) => !only || only.includes(check);
const RUNS = Number(option("runs") ?? 5);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- Chrome over the debugging protocol -------------------------------------------------------

async function launchChrome() {
  const profile = mkdtempSync(join(tmpdir(), "tmooi-audit-"));
  const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--no-first-run", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
  for (let i = 0; i < 50; i++) {
    try {
      if ((await fetch(`http://127.0.0.1:${PORT}/json/version`)).ok) break;
    } catch {}
    await sleep(100);
  }
  return async () => {
    // Wait for Chrome to exit before removing its profile, or the folder is still being written to.
    const exited = new Promise((r) => chrome.once("exit", r));
    chrome.kill();
    await exited;
    rmSync(profile, { recursive: true, force: true });
  };
}

/** One page, one WebSocket. Commands get an id; replies and events come back on the same socket. */
async function openPage() {
  const { webSocketDebuggerUrl } = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json();
  const ws = new WebSocket(webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });
  let nextId = 1;
  const pending = new Map();
  const listeners = new Set();
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    } else if (msg.method) for (const fn of listeners) fn(msg);
  };
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  const once = (method) =>
    new Promise((resolve) => {
      const fn = (msg) => {
        if (msg.method === method) {
          listeners.delete(fn);
          resolve(msg.params);
        }
      };
      listeners.add(fn);
    });
  /** Runs an expression in the page and returns its value (promises are awaited). */
  const run = async (expression) => {
    const { result, exceptionDetails } = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
    return result.value;
  };
  return { send, once, run, close: () => ws.close() };
}

/** Opens a page at a size and address and waits for the gallery to have loaded. */
async function visit(path, { width = 1024, height = 800, mobile = false, openHood = false } = {}) {
  const page = await openPage();
  await page.send("Page.enable");
  await page.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile });
  const loaded = page.once("Page.loadEventFired");
  await page.send("Page.navigate", { url: `${base}${path}` });
  await loaded;
  await sleep(2500); // the gallery index and the transcript are fetched after load
  // Under the hood is always open now; give its lazily loaded panels time to arrive.
  if (openHood) await sleep(2500);
  return page;
}

// ---- Checks -----------------------------------------------------------------------------------

const KEEP = new Set(["banner", "main", "contentinfo", "region", "heading", "button", "link", "slider", "log", "status", "img", "list", "article", "navigation", "alert"]);
const NEEDS_NAME = new Set(["button", "link", "slider", "heading", "img"]);

async function checkTree(sessionPath) {
  console.log("\n== Accessibility tree ==");
  for (const [title, path, openHood] of [["Home page", "/", false], ["A session, Under the hood open", sessionPath, true]]) {
    const page = await visit(path, { openHood });
    await page.send("Accessibility.enable");
    const { nodes } = await page.send("Accessibility.getFullAXTree");
    const lang = await page.run("document.documentElement.lang");
    const byId = new Map(nodes.map((n) => [n.nodeId, n]));
    const lines = [];
    const problems = [];
    let lastLevel = 0;
    let hasMain = false;
    // `shown` counts the buttons printed under the nearest printed ancestor, so a list of twenty
    // trace steps prints four and says how many more there are.
    const walk = (node, depth, shown) => {
      const role = node.role?.value;
      const keep = !node.ignored && KEEP.has(role);
      if (keep && role === "button") {
        if (shown.buttons >= 4) {
          shown.hidden += 1;
          if (!(node.name?.value ?? "").trim()) problems.push("button with no accessible name");
          return;
        }
        shown.buttons += 1;
      }
      const own = keep ? { buttons: 0, hidden: 0 } : shown;
      if (keep) {
        const name = (node.name?.value ?? "").replace(/\s+/g, " ").trim();
        const level = node.properties?.find((p) => p.name === "level")?.value?.value;
        // (Chrome's protocol never reports aria-valuetext or aria-current, so those can't show here.)
        const state = (node.properties ?? []).filter((p) => ["expanded", "pressed", "live"].includes(p.name)).map((p) => `${p.name}=${p.value.value}`);
        if (role === "main") hasMain = true;
        if (role === "heading") {
          if (level > lastLevel + 1) problems.push(`heading level jumps from ${lastLevel} to ${level}: "${name}"`);
          lastLevel = level;
        }
        if (NEEDS_NAME.has(role) && !name) problems.push(`${role} with no accessible name`);        lines.push(`${"  ".repeat(depth)}${role}${level ? ` h${level}` : ""}${name ? ` "${name.slice(0, 90)}"` : ""}${state.length ? ` [${state.join(" ")}]` : ""}`);
      }
      for (const id of node.childIds ?? []) if (byId.has(id)) walk(byId.get(id), keep ? depth + 1 : depth, own);
      if (keep && own.hidden > 0) lines.push(`${"  ".repeat(depth + 1)}... ${own.hidden} more buttons`);
    };
    walk(nodes[0], 0, { buttons: 0, hidden: 0 });
    if (!hasMain) problems.push("no <main> landmark");
    if (!lang) problems.push("the page has no lang attribute");
    console.log(`\n-- ${title} (${path})\n${lines.join("\n")}\n-- Flags: ${problems.length ? "\n   " + problems.join("\n   ") : "none"}`);
    page.close();
  }
}

// Runs in the page. Works out each text's color and the color behind it (stacking semi-transparent
// backgrounds up to the first solid one), through a 1 px canvas so any CSS color (color-mix, oklab)
// turns into plain RGB.
const CONTRAST_SCRIPT = `(() => {
  const cv = document.createElement('canvas'); cv.width = cv.height = 1;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  const rgba = (css) => { cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#000'; cx.fillStyle = css; cx.fillRect(0, 0, 1, 1); const d = cx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const over = (top, under) => { const a = top[3]; return [top[0] * a + under[0] * (1 - a), top[1] * a + under[1] * (1 - a), top[2] * a + under[2] * (1 - a), 1]; };
  const behind = (el) => { const layers = []; let image = false; for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.backgroundImage !== 'none') image = true; const c = rgba(cs.backgroundColor); if (c[3] > 0) { layers.push(c); if (c[3] === 1) break; } } let base = rgba(getComputedStyle(document.body).backgroundColor); for (const l of layers.reverse()) base = over(l, base); return { bg: base, image }; };
  const found = new Map(); let measured = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode()); ) {
    const text = n.textContent.trim(); if (!text) continue;
    const el = n.parentElement; if (!el || el.closest('.sr-only')) continue;
    const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
    if (cs.visibility === 'hidden' || cs.display === 'none' || r.width === 0 || r.height === 0) continue;
    let opacity = 1; for (let e = el; e; e = e.parentElement) opacity *= Number(getComputedStyle(e).opacity);
    if (opacity < 0.05) continue;
    const { bg, image } = behind(el);
    let fg = rgba(cs.color); if (fg[3] === 0) continue; fg = over(fg, bg); if (opacity < 1) fg = over([fg[0], fg[1], fg[2], opacity], bg);
    const L1 = lum(fg), L2 = lum(bg); const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const px = parseFloat(cs.fontSize); const large = px >= 24 || (px >= 18.66 && Number(cs.fontWeight) >= 700);
    measured++;
    if (ratio < (large ? 3 : 4.5)) { const key = cs.color + '|' + bg.map(Math.round) + '|' + px; if (!found.has(key)) found.set(key, { ratio: +ratio.toFixed(2), px, sample: text.slice(0, 40), image }); }
  }
  return { measured, failures: [...found.values()] };
})()`;

async function checkContrast(sessionPath) {
  console.log("\n== Text contrast (WCAG AA) ==");
  const page = await visit(sessionPath, { openHood: true });
  const { measured, failures } = await page.run(CONTRAST_SCRIPT);
  console.log(`${measured} pieces of text measured; ${failures.length === 0 ? "none below the threshold" : `${failures.length} below it:`}`);
  for (const f of failures) console.log(`  ${f.ratio} to 1 at ${f.px}px: "${f.sample}"${f.image ? " (over a gradient or image: check by eye)" : ""}`);
  page.close();
}

async function checkReflow(sessionPath) {
  console.log("\n== A 320 px wide screen ==");
  for (const [title, path, openHood] of [["Home page", "/", false], ["A session, Under the hood open", sessionPath, true]]) {
    const page = await visit(path, { width: 320, height: 700, mobile: true, openHood });
    const report = await page.run(`(() => {
      const de = document.documentElement;
      const small = [];
      for (const el of document.querySelectorAll('a[href], button, summary, [role=slider], input, select, textarea')) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0 || (r.width >= 24 && r.height >= 24)) continue;
        const stretched = getComputedStyle(el, '::after').position === 'absolute'; // the whole card is the target
        if (!stretched) small.push((el.getAttribute('aria-label') || el.innerText || el.tagName).trim().replace(/\\s+/g, ' ').slice(0, 40) + ' (' + Math.round(r.width) + ' by ' + Math.round(r.height) + ')');
      }
      return { sideways: de.scrollWidth > de.clientWidth, small };
    })()`);
    console.log(`-- ${title}: ${report.sideways ? "SCROLLS SIDEWAYS" : "no sideways scroll"}; controls under 24 by 24 px: ${report.small.length ? "\n   " + report.small.join("\n   ") : "none"}`);
    page.close();
  }
}

// Runs in every page before it loads: records when things painted and appeared.
const OBSERVER = `
  window.__m = { fcp: null, lcp: null, cls: 0, cards: null };
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (e.name === 'first-contentful-paint') __m.fcp = e.startTime; }).observe({ type: 'paint', buffered: true });
  new PerformanceObserver((l) => { const es = l.getEntries(); __m.lcp = es[es.length - 1].startTime; }).observe({ type: 'largest-contentful-paint', buffered: true });
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) __m.cls += e.value; }).observe({ type: 'layout-shift', buffered: true });
  new MutationObserver(() => { if (__m.cards === null && document.querySelector('#gallery ul li')) __m.cards = performance.now(); }).observe(document, { childList: true, subtree: true });
`;

async function slowVisit({ cache }) {
  const page = await openPage();
  try {
    await page.send("Page.enable");
    await page.send("Network.enable");
    await page.send("Emulation.setDeviceMetricsOverride", { width: 412, height: 823, deviceScaleFactor: 2, mobile: true });
    await page.send("Emulation.setCPUThrottlingRate", { rate: 4 });
    await page.send("Network.emulateNetworkConditions", { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 });
    await page.send("Network.setCacheDisabled", { cacheDisabled: !cache });
    await page.send("Page.addScriptToEvaluateOnNewDocument", { source: OBSERVER });
    const loaded = page.once("Page.loadEventFired");
    await page.send("Page.navigate", { url: `${base}/` });
    await loaded;
    for (let i = 0; i < 40 && !(await page.run("__m.cards !== null")); i++) await sleep(250);
    await sleep(2500); // let the largest paint and any layout shift settle
    return await page.run(`(() => {
      const nav = performance.getEntriesByType('navigation')[0];
      const res = performance.getEntriesByType('resource');
      return { fcp: __m.fcp, lcp: __m.lcp, cards: __m.cards, cls: __m.cls, requests: res.length + 1,
        kb: [nav, ...res].reduce((s, r) => s + (r.transferSize || 0), 0) / 1024,
        asked: res.filter((r) => r.transferSize > 0 && r.transferSize < 400 && r.encodedBodySize > 0).length,
        cached: res.filter((r) => r.transferSize === 0 && r.decodedBodySize > 0).length };
    })()`);
  } finally {
    page.close();
  }
}

async function checkPerf() {
  console.log(`\n== Load speed: Slow 4G, 4x slower processor, phone screen (median of ${RUNS}) ==`);
  const median = (xs) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)];
  const cold = [];
  for (let i = 0; i < RUNS; i++) cold.push(await slowVisit({ cache: false }));
  await slowVisit({ cache: true }); // fills the cache
  const warm = [];
  for (let i = 0; i < RUNS; i++) warm.push(await slowVisit({ cache: true }));
  const row = (label, rows) =>
    `${label.padEnd(14)} first paint ${String(Math.round(median(rows.map((r) => r.fcp)))).padStart(5)} ms | largest paint ${String(Math.round(median(rows.map((r) => r.lcp)))).padStart(5)} ms | gallery shown ${String(Math.round(median(rows.map((r) => r.cards)))).padStart(5)} ms | layout shift ${median(rows.map((r) => r.cls)).toFixed(3)} | ${median(rows.map((r) => r.kb)).toFixed(1).padStart(6)} KB in ${median(rows.map((r) => r.requests))} requests (${median(rows.map((r) => r.cached))} from cache, ${median(rows.map((r) => r.asked))} asked "changed?")`;
  console.log(row("First visit", cold));
  console.log(row("Return visit", warm));
}

// ---- Run --------------------------------------------------------------------------------------

const closeChrome = await launchChrome();
try {
  const index = await (await fetch(`${base}/gallery/index.json`)).json();
  const councilSession = index.sessions.find((s) => s.kind === "council") ?? index.sessions[0];
  const sessionPath = `/s/${councilSession.id}`;
  console.log(`Auditing ${base} (session page: ${sessionPath})`);
  if (wants("tree")) await checkTree(sessionPath);
  if (wants("contrast")) await checkContrast(sessionPath);
  if (wants("reflow")) await checkReflow(sessionPath);
  if (wants("perf")) await checkPerf();
} finally {
  await closeChrome();
}
