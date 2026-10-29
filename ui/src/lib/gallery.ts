/*
  The shape of sessions/gallery/index.json, which the engine writes (session_store.py) and the
  UI only reads. If the UI ever needs a field that is not here, the engine and session_schema.py
  change first, never the JSON by hand.
*/

export type Verdict = "buy" | "wait" | "skip";

export interface GallerySession {
  id: string;
  file: string;
  kind: "council" | "declined";
  item: string;
  price: number;
  want_level: number;
  current_device: string | null;
  created_at: string;
  model: string;
  verdict: Verdict | null;
  verdict_label: string | null;
  score: number | null;
  rail: string | null;
  /** The code-written sentence for a rail, when the engine includes it in the index. */
  rail_note?: string | null;
  rounds: number;
  seconds: number;
  ruling: string | null;
  why_featured: string;
  judge_fallback: boolean | null;
  pool_id: string | null;
}

export interface GalleryIndex {
  about: string;
  count: number;
  sessions: GallerySession[];
}

/** Where the static files live. Vite fills BASE_URL in ("/" in dev and on Cloudflare Pages). */
export const GALLERY_URL = `${import.meta.env.BASE_URL}gallery/`;

export async function loadGalleryIndex(): Promise<GalleryIndex> {
  const response = await fetch(`${GALLERY_URL}index.json`);
  if (!response.ok) {
    throw new Error(`Could not load the gallery index (${response.status}).`);
  }
  const data: unknown = await response.json();
  if (!isGalleryIndex(data)) {
    throw new Error("The gallery index is not in the shape the UI expects.");
  }
  return data;
}

function isGalleryIndex(data: unknown): data is GalleryIndex {
  if (typeof data !== "object" || data === null) return false;
  const record = data as Record<string, unknown>;
  return (
    Array.isArray(record.sessions) &&
    record.sessions.every(
      (s) => typeof s === "object" && s !== null && typeof (s as GallerySession).id === "string",
    )
  );
}

/** Lives in page-text.ts so the build step can use it too; re-exported here for the components. */
export { formatPrice } from "@/lib/page-text";

export function formatDuration(seconds: number): string {
  const whole = Math.round(seconds);
  const minutes = Math.floor(whole / 60);
  const rest = whole % 60;
  if (minutes === 0) return `${rest} s`;
  return rest === 0 ? `${minutes} min` : `${minutes} min ${rest} s`;
}
