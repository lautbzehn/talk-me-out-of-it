/*
  The words that name a session outside the app: the browser tab, and the title and description
  a link preview shows. One place, so the tab, the preview and the share card never say
  different things about the same verdict.

  This file is used from two sides. The app imports it as usual. The build step
  (scripts/write-previews.mjs) imports it straight from Node, which can run TypeScript by
  stripping the type annotations. That only works if this file stands alone: no "@/..." imports,
  no import.meta.env, nothing from React or the browser.
*/

export const SITE_TITLE = "Talk Me Out of It";

/** The fields of a gallery session that the page text reads. GallerySession has all of them. */
export interface NamedSession {
  kind: "council" | "declined";
  item: string;
  price: number;
  verdict_label: string | null;
  score: number | null;
  ruling: string | null;
}

export function formatPrice(price: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: price % 1 === 0 ? 0 : 2,
  }).format(price);
}

/** "PlayStation 5 Pro: Wait 30 days · Talk Me Out of It" */
export function pageTitle(session: NamedSession): string {
  return `${session.item}: ${session.verdict_label ?? "declined"} · ${SITE_TITLE}`;
}

/** Link previews cut off around 200 characters, so keep it under that, ending on a whole word. */
const DESCRIPTION_LIMIT = 200;

export function pageDescription(session: NamedSession): string {
  if (session.kind !== "council" || session.score === null || !session.verdict_label) {
    return `${session.item} is not a gadget, so the council politely declined it instead of debating it.`;
  }
  const lead = `${session.verdict_label} at ${session.score.toFixed(1)} of 10 for ${formatPrice(session.price)}.`;
  const text = session.ruling ? `${lead} ${session.ruling}` : lead;
  if (text.length <= DESCRIPTION_LIMIT) return text;
  const cut = text.slice(0, DESCRIPTION_LIMIT - 1);
  return `${cut.slice(0, cut.lastIndexOf(" "))}…`;
}

/** What the preview image says, for people who cannot see it. */
export function imageAlt(session: NamedSession): string {
  if (session.kind !== "council" || session.score === null || !session.verdict_label) {
    return `Share card: ${session.item}, declined because it is not a gadget.`;
  }
  return `Share card: ${session.item}, ${session.verdict_label} at ${session.score.toFixed(1)} of 10.`;
}
