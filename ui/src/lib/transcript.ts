/*
  The part of a full session transcript (sessions/gallery/<file>.json) that the debate replay
  reads. The engine writes these files (session_schema.py) and the UI only reads them, so only
  the fields the UI uses are typed here. Everything else in the file (traces, the engine block,
  the scoring inputs) is read separately and leniently by lib/hood.ts for "Under the hood".
*/
import { GALLERY_URL } from "@/lib/gallery";
import { parseHood, type Hood } from "@/lib/hood";

export type Lean = "buy" | "wait" | "skip";
export type RoundKind = "opening" | "rebuttal" | "tiebreak";

/** What an agent said in a turn. An opening turn has `take`; a rebuttal or tiebreak has `response`. */
export interface TurnText {
  take?: string;
  responding_to?: string[];
  response?: string;
  lean: Lean;
  confidence: number;
}

export interface TurnChanges {
  lean: { from: Lean; to: Lean };
}

export interface Turn {
  agent: string;
  /** "ok", or "failed" when every attempt was rejected and the member sat out. */
  status: string;
  take_or_rebuttal: TurnText | null;
  changes: TurnChanges | null;
  /** How long the model took, in real seconds. The replay scales its typing time from this. */
  seconds: number;
}

export interface Round {
  number: number;
  kind: RoundKind;
  seconds: number;
  turns: Turn[];
}

export interface JudgeRecord {
  summary: string;
  /** True when the Judge's answer failed its checks and code wrote the summary instead. */
  fallback_used: boolean;
  seconds: number;
}

export interface Transcript {
  kind: "council" | "declined";
  rounds: Round[];
  judge: JudgeRecord | null;
  /** What "Under the hood" shows, parsed leniently (lib/hood.ts). Null if the file has none of it. */
  hood: Hood | null;
}

const LEANS: readonly string[] = ["buy", "wait", "skip"];
const ROUND_KINDS: readonly string[] = ["opening", "rebuttal", "tiebreak"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Throws a plain-English message naming what is wrong and where. */
function fail(where: string, problem: string): never {
  throw new Error(`The transcript is not in the shape the UI expects: ${where} ${problem}.`);
}

function parseText(value: unknown, where: string): TurnText {
  if (!isRecord(value)) fail(where, "is not an object");
  if (typeof value.lean !== "string" || !LEANS.includes(value.lean)) fail(`${where}.lean`, "is not buy, wait or skip");
  const hasWords = typeof value.take === "string" || typeof value.response === "string";
  if (!hasWords) fail(where, "has neither a take nor a response");
  if (value.responding_to !== undefined && !(Array.isArray(value.responding_to) && value.responding_to.every((n) => typeof n === "string"))) {
    fail(`${where}.responding_to`, "is not a list of names");
  }
  return value as unknown as TurnText;
}

function parseChanges(value: unknown, where: string): TurnChanges | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value) || !isRecord(value.lean)) fail(where, "has no lean change record");
  const { from, to } = value.lean;
  if (typeof from !== "string" || !LEANS.includes(from) || typeof to !== "string" || !LEANS.includes(to)) {
    fail(`${where}.lean`, "does not hold two leans");
  }
  return { lean: { from: from as Lean, to: to as Lean } };
}

function parseTurn(value: unknown, where: string): Turn {
  if (!isRecord(value)) fail(where, "is not an object");
  if (typeof value.agent !== "string") fail(`${where}.agent`, "is not a name");
  if (typeof value.status !== "string") fail(`${where}.status`, "is missing");
  if (typeof value.seconds !== "number") fail(`${where}.seconds`, "is not a number");
  const text = value.take_or_rebuttal === null || value.take_or_rebuttal === undefined ? null : parseText(value.take_or_rebuttal, `${where}.take_or_rebuttal`);
  return {
    agent: value.agent,
    status: value.status,
    take_or_rebuttal: text,
    changes: parseChanges(value.changes, `${where}.changes`),
    seconds: value.seconds,
  };
}

function parseRound(value: unknown, where: string): Round {
  if (!isRecord(value)) fail(where, "is not an object");
  if (typeof value.number !== "number") fail(`${where}.number`, "is not a number");
  if (typeof value.kind !== "string" || !ROUND_KINDS.includes(value.kind)) fail(`${where}.kind`, "is not opening, rebuttal or tiebreak");
  if (typeof value.seconds !== "number") fail(`${where}.seconds`, "is not a number");
  if (!Array.isArray(value.turns)) fail(`${where}.turns`, "is not a list");
  return {
    number: value.number,
    kind: value.kind as RoundKind,
    seconds: value.seconds,
    turns: value.turns.map((turn, i) => parseTurn(turn, `${where}.turns[${i}]`)),
  };
}

function parseJudge(value: unknown): JudgeRecord | null {
  if (!isRecord(value) || typeof value.summary !== "string" || typeof value.seconds !== "number") return null;
  return { summary: value.summary, fallback_used: value.fallback_used === true, seconds: value.seconds };
}

export function parseTranscript(data: unknown): Transcript {
  if (!isRecord(data)) fail("the file", "is not an object");
  if (data.kind !== "council" && data.kind !== "declined") fail("kind", "is not council or declined");
  if (!Array.isArray(data.rounds)) fail("rounds", "is not a list");
  return {
    kind: data.kind,
    rounds: data.rounds.map((round, i) => parseRound(round, `rounds[${i}]`)),
    judge: parseJudge(data.judge),
    hood: parseHood(data),
  };
}

/* A visitor who flips between chips and back should not download the same file twice. */
const cache = new Map<string, Promise<Transcript>>();

export function loadTranscript(file: string): Promise<Transcript> {
  const cached = cache.get(file);
  if (cached) return cached;
  const pending = fetch(`${GALLERY_URL}${file}`)
    .then((response) => {
      if (!response.ok) throw new Error(`Could not load the debate (${response.status}).`);
      return response.json() as Promise<unknown>;
    })
    .then(parseTranscript);
  cache.set(file, pending);
  pending.catch(() => cache.delete(file));
  return pending;
}
