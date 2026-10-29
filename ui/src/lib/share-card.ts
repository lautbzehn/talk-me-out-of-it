/*
  The share cards: pictures of one verdict (and of the home page), drawn on a <canvas> in the
  visitor's own browser and handed over as a PNG. No package and no server: the canvas uses the
  fonts the page has already loaded and the colors from index.css, so a card matches the site.

  1200 by 630 is the shape link previews use. The "Share image" button draws at twice that so
  the picture stays sharp on a phone screen; the export tool (export.html) draws at 1x to make
  the preview images the build step points link previews at.

  Every word and number on a verdict card comes from the gallery index; the only fixed text is
  the site name, the labels and the disclaimer.
*/
import { formatPrice, type GallerySession, type Verdict } from "@/lib/gallery";

export const CARD_WIDTH = 1200;
export const CARD_HEIGHT = 630;

const PAD = 72;
const MONO = `"Geist Mono Variable", ui-monospace, "SF Mono", Menlo, monospace`;
const SANS = `"Geist Variable", ui-sans-serif, system-ui, sans-serif`;
const WAIT_AT = 4.5;
const BUY_AT = 5.5;
const AGENT_TOKENS = ["--agent-analyst", "--agent-future", "--agent-guardian", "--agent-hunter", "--agent-judge"];

function token(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

/** "#e78a53" with an alpha, as rgba(). The tokens in index.css are all six-digit hex. */
function alpha(hex: string, a: number): string {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!m) return hex;
  return `rgba(${parseInt(m[1] ?? "0", 16)}, ${parseInt(m[2] ?? "0", 16)}, ${parseInt(m[3] ?? "0", 16)}, ${a})`;
}

/** Splits text into lines that fit, ending the last allowed line with "…" if it runs over. */
function wrap(ctx: CanvasRenderingContext2D, text: string, width: number, maxLines: number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const test = line ? `${line} ${word}` : word;
    if (line && ctx.measureText(test).width > width) {
      lines.push(line);
      line = word;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  let last = kept[maxLines - 1] ?? "";
  while (ctx.measureText(`${last}…`).width > width && last.includes(" ")) last = last.slice(0, last.lastIndexOf(" "));
  kept[maxLines - 1] = `${last}…`;
  return kept;
}

function fitOneLine(ctx: CanvasRenderingContext2D, text: string, width: number): string {
  return wrap(ctx, text, width, 1)[0] ?? "";
}

function percentOnScale(value: number): number {
  return (Math.min(10, Math.max(1, value)) - 1) / 9;
}

type Colors = ReturnType<typeof colors>;

function colors() {
  return {
    background: token("--background", "#121113"),
    card: token("--card", "#121212"),
    muted: token("--muted", "#222222"),
    mutedForeground: token("--muted-foreground", "#8f8f8f"),
    foreground: token("--foreground", "#c1c1c1"),
    strong: token("--foreground-strong", "#f2efea"),
    border: token("--border", "#262626"),
    primary: token("--primary", "#e78a53"),
    future: token("--agent-future", "#a78bfa"),
    analyst: token("--agent-analyst", "#5fb3b3"),
  };
}

const verdictColor = (v: Verdict) => token(`--verdict-${v}`, "#fbbf24");

/** The page's fonts may not have been needed yet at these weights; wait so the canvas never falls back. */
async function loadFonts(): Promise<void> {
  await Promise.all([
    document.fonts.load(`600 56px ${MONO}`),
    document.fonts.load(`400 24px ${MONO}`),
    document.fonts.load(`400 30px ${SANS}`),
  ]);
}

function startCanvas(scale: number): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D } {
  const canvas = document.createElement("canvas");
  canvas.width = CARD_WIDTH * scale;
  canvas.height = CARD_HEIGHT * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("This browser cannot draw the card.");
  ctx.scale(scale, scale);
  ctx.textBaseline = "alphabetic";
  return { canvas, ctx };
}

/** The background, the aurora (as on the landing page) and the card's frame. */
function paintBackdrop(ctx: CanvasRenderingContext2D, c: Colors): void {
  ctx.fillStyle = c.background;
  ctx.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);
  const glow = (x: number, y: number, r: number, color: string, a: number) => {
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, alpha(color, a));
    g.addColorStop(1, alpha(color, 0));
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);
  };
  glow(80, 0, 620, c.future, 0.26);
  glow(1160, 40, 560, c.analyst, 0.2);
  glow(640, 700, 520, c.primary, 0.14);

  ctx.beginPath();
  ctx.roundRect(24, 24, CARD_WIDTH - 48, CARD_HEIGHT - 48, 28);
  ctx.fillStyle = alpha(c.card, 0.6);
  ctx.fill();
  ctx.strokeStyle = c.border;
  ctx.lineWidth = 2;
  ctx.stroke();
}

/** The council's five orbs in an overlapping row, left edge at `x`, `radius` pixels each. */
function paintOrbs(ctx: CanvasRenderingContext2D, c: Colors, x: number, y: number, radius: number, step: number): number {
  for (const name of AGENT_TOKENS) {
    const color = token(name, "#8f8f8f");
    const g = ctx.createRadialGradient(x - radius * 0.35, y - radius * 0.45, 2, x, y + radius * 0.2, radius * 1.15);
    g.addColorStop(0, "#ffffff");
    g.addColorStop(0.25, color);
    g.addColorStop(1, color);
    ctx.beginPath();
    ctx.arc(x, y, radius + 3, 0, Math.PI * 2);
    ctx.fillStyle = c.background;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fillStyle = g;
    ctx.fill();
    x += step;
  }
  return x;
}

/** The disclaimer, and the address the card came from, so a saved image still leads back here. */
function paintFooter(ctx: CanvasRenderingContext2D, c: Colors, host: string | null): void {
  ctx.font = `400 16px ${MONO}`;
  ctx.fillStyle = c.mutedForeground;
  ctx.textAlign = "left";
  ctx.fillText("Argued by a council of AI agents. A decision helper, not financial advice.", PAD, CARD_HEIGHT - 50);
  if (host) {
    ctx.textAlign = "right";
    ctx.fillText(host, CARD_WIDTH - PAD, CARD_HEIGHT - 50);
    ctx.textAlign = "left";
  }
}

function toPng(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("The card could not be saved as an image."))), "image/png"),
  );
}

/**
  `host` is printed in the footer. It defaults to the address the page is served from, which is
  right for a visitor saving a card. The export tool passes null: the preview images are public
  files, and a link preview already shows the domain, so they must not carry "localhost:5173".
*/
export async function drawShareCard(session: GallerySession, scale = 2, host: string | null = window.location.host): Promise<Blob> {
  await loadFonts();
  const c = colors();
  const { canvas, ctx } = startCanvas(scale);
  paintBackdrop(ctx, c);

  // Header: the council's five orbs and the site's name.
  const afterOrbs = paintOrbs(ctx, c, PAD + 14, 82, 14, 22);
  ctx.font = `600 24px ${MONO}`;
  ctx.fillStyle = c.strong;
  ctx.fillText("Talk Me Out of It", afterOrbs + 12, 90);
  ctx.font = `500 15px ${MONO}`;
  ctx.fillStyle = c.mutedForeground;
  ctx.textAlign = "right";
  ctx.fillText(session.kind === "council" ? "THE COUNCIL'S VERDICT" : "THE COUNCIL DECLINED", CARD_WIDTH - PAD, 88);
  ctx.textAlign = "left";

  const width = CARD_WIDTH - PAD * 2;
  let y = 172;

  // The item and its facts.
  ctx.font = `600 52px ${MONO}`;
  ctx.fillStyle = c.strong;
  for (const line of wrap(ctx, session.item, width, 2)) {
    ctx.fillText(line, PAD, y);
    y += 60;
  }
  ctx.font = `400 22px ${MONO}`;
  ctx.fillStyle = c.mutedForeground;
  const facts = [formatPrice(session.price), `want ${session.want_level} of 10`, session.current_device ? `replaces ${session.current_device}` : null]
    .filter(Boolean)
    .join(" · ");
  ctx.fillText(fitOneLine(ctx, facts, width), PAD, y - 18);
  y += 24;

  if (session.kind !== "council" || session.verdict === null || session.score === null) {
    ctx.font = `600 64px ${MONO}`;
    ctx.fillStyle = c.strong;
    ctx.fillText("Not a gadget.", PAD, y + 70);
    ctx.font = `400 28px ${SANS}`;
    ctx.fillStyle = c.foreground;
    let ty = y + 130;
    // A narrower column than the card's, so the two lines break evenly and no word is left alone.
    for (const line of wrap(ctx, "The council only argues about tech. It declined this one politely instead of debating it.", 820, 2)) {
      ctx.fillText(line, PAD, ty);
      ty += 40;
    }
  } else {
    const verdict = session.verdict;
    const color = verdictColor(verdict);

    // The score, "of 10", and the verdict pill.
    const baseline = y + 104;
    ctx.font = `600 120px ${MONO}`;
    ctx.fillStyle = c.strong;
    const scoreText = session.score.toFixed(1);
    ctx.fillText(scoreText, PAD - 4, baseline);
    let px = PAD + ctx.measureText(scoreText).width + 12;
    ctx.font = `400 26px ${MONO}`;
    ctx.fillStyle = c.mutedForeground;
    ctx.fillText("of 10", px, baseline);
    px += ctx.measureText("of 10").width + 28;
    ctx.font = `600 26px ${MONO}`;
    const label = session.verdict_label ?? verdict;
    const pillWidth = ctx.measureText(label).width + 64;
    ctx.beginPath();
    ctx.roundRect(px, baseline - 42, pillWidth, 52, 26);
    ctx.fillStyle = alpha(color, 0.16);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(px + 26, baseline - 16, 6, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.fillText(label, px + 42, baseline - 7);

    // The 1-to-10 scale with the Wait and Buy lines.
    const barY = baseline + 52;
    ctx.beginPath();
    ctx.roundRect(PAD, barY, width, 12, 6);
    ctx.fillStyle = c.muted;
    ctx.fill();
    ctx.beginPath();
    ctx.roundRect(PAD, barY, Math.max(12, width * percentOnScale(session.score)), 12, 6);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.font = `400 14px ${MONO}`;
    ctx.textAlign = "center";
    for (const at of [WAIT_AT, BUY_AT]) {
      const tx = PAD + width * percentOnScale(at);
      ctx.fillStyle = c.mutedForeground;
      ctx.fillRect(tx - 1, barY - 8, 2, 28);
      ctx.fillText(String(at), tx, barY - 14);
    }
    ctx.textAlign = "left";

    // The Judge's one-line reason, and the code-written rule note when a rule held the verdict.
    let ty = barY + 64;
    ctx.font = `400 28px ${SANS}`;
    ctx.fillStyle = c.strong;
    // As many lines (one or two) as fit above the footer, leaving room for the rule note.
    const lastBaseline = CARD_HEIGHT - 50 - 42;
    const room = session.rail_note ? lastBaseline - 32 : lastBaseline;
    const maxLines = Math.max(1, Math.min(2, Math.floor((room - ty) / 38) + 1));
    for (const line of wrap(ctx, session.ruling ?? "", width, maxLines)) {
      ctx.fillText(line, PAD, ty);
      ty += 38;
    }
    if (session.rail_note) {
      ctx.font = `400 20px ${SANS}`;
      ctx.fillStyle = c.foreground;
      ctx.fillText(fitOneLine(ctx, `Rule: ${session.rail_note}`, width), PAD, ty + 2);
    }
  }

  paintFooter(ctx, c, host);
  return toPng(canvas);
}

/** The home page's card: the name, the hook with the three verdicts in their colors, the five orbs. */
export async function drawHomeCard(scale = 1, host: string | null = window.location.host): Promise<Blob> {
  await loadFonts();
  const c = colors();
  const { canvas, ctx } = startCanvas(scale);
  paintBackdrop(ctx, c);

  // The council, centered. Five orbs 44 px across, overlapping by 12.
  const radius = 26;
  const step = 40;
  paintOrbs(ctx, c, CARD_WIDTH / 2 - (step * 4) / 2, 170, radius, step);

  // The name, with the landing page's warm glow.
  ctx.textAlign = "center";
  ctx.font = `600 96px ${MONO}`;
  ctx.fillStyle = c.strong;
  ctx.save();
  ctx.shadowColor = alpha(c.primary, 0.55);
  ctx.shadowBlur = 44;
  ctx.fillText("Talk Me Out of It", CARD_WIDTH / 2, 328);
  ctx.restore();
  ctx.fillText("Talk Me Out of It", CARD_WIDTH / 2, 328);

  // The hook: one line in the body color, one line with the verdicts colored.
  ctx.font = `400 34px ${SANS}`;
  ctx.fillStyle = c.foreground;
  ctx.fillText("A council of AI agents argues about the gadget you want,", CARD_WIDTH / 2, 408);
  const parts: [string, string][] = [
    ["then rules: ", c.foreground],
    ["Buy", verdictColor("buy")],
    [", ", c.foreground],
    ["Wait 30 days", verdictColor("wait")],
    [", or ", c.foreground],
    ["Skip", verdictColor("skip")],
    [".", c.foreground],
  ];
  ctx.textAlign = "left";
  let x = (CARD_WIDTH - parts.reduce((sum, [t]) => sum + ctx.measureText(t).width, 0)) / 2;
  for (const [t, color] of parts) {
    ctx.fillStyle = color;
    ctx.fillText(t, x, 458);
    x += ctx.measureText(t).width;
  }

  paintFooter(ctx, c, host);
  return toPng(canvas);
}
