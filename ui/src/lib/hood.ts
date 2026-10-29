/*
  The parts of a transcript that "Under the hood" shows: every model call, tool call and answer
  attempt with its timing and tokens, the intake check and the injection guard, the scoring
  block, the engine's rules, and each member's brief.

  The debate (lib/transcript.ts) refuses a file it cannot play. This parser is the opposite: it
  never throws. Anything missing or malformed comes back as null or an empty list, so an odd
  trace can only hide a detail in this panel, never break the debate above it.
*/
import type { Lean, RoundKind } from "@/lib/transcript";

export interface ModelCall {
  step: number;
  seconds: number;
  promptTokens: number;
  outputTokens: number;
  toolCallsRequested: number;
}

export interface ToolCall {
  step: number;
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  result: Record<string, unknown> | null;
  error: string | null;
  seconds: number;
}

/** One try at the final answer. Rejected tries carry the validator's message in `error`. */
export interface Attempt {
  attempt: number;
  seconds: number;
  promptTokens: number;
  outputTokens: number;
  ok: boolean;
  error: string | null;
}

export interface Rating {
  reason: string;
  score: number;
}

export interface HoodTurn {
  agent: string;
  status: string;
  seconds: number;
  lean: Lean | null;
  ratings: Record<string, Rating>;
  modelCalls: ModelCall[];
  toolCalls: ToolCall[];
  attempts: Attempt[];
}

export interface HoodRound {
  number: number;
  kind: RoundKind;
  seconds: number;
  turns: HoodTurn[];
}

export interface Scoring {
  score: number;
  verdict: Lean;
  verdictLabel: string;
  scoreVerdict: Lean;
  /** Each member's final ratings, by rubric key. A member who sat out is not here. */
  inputs: Record<string, Record<string, number>>;
  notCounted: string[];
  ratingsCounted: number;
  leans: Record<string, Lean>;
  rail: string | null;
  railNote: string | null;
}

export interface Rules {
  buyAt: number;
  waitAt: number;
  weights: Record<string, number>;
  maxRounds: number | null;
  maxAttempts: number | null;
  temperature: number | null;
  contextTokens: number | null;
}

export interface Member {
  name: string;
  focus: string;
  voice: string;
  rubric: Record<string, string>;
  tools: string[];
  requiredTools: string[];
  systemPrompt: string;
}

export interface Hood {
  kind: "council" | "declined";
  model: string;
  intake: { note: string; isGadget: boolean; category: string | null; seconds: number; attempts: Attempt[] };
  guard: { triggered: boolean; by: string[]; removed: string[] };
  rounds: HoodRound[];
  judge: { seconds: number; fallbackUsed: boolean; attempts: Attempt[] } | null;
  totalSeconds: number;
  scoring: Scoring | null;
  rules: Rules | null;
  members: Member[];
  judgePrompt: string | null;
}

const LEANS: readonly string[] = ["buy", "wait", "skip"];
const ROUND_KINDS: readonly string[] = ["opening", "rebuttal", "tiebreak"];

type Raw = Record<string, unknown>;

function rec(value: unknown): Raw | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Raw) : null;
}
function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}
function num(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
function numOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}
function strOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}
function lean(value: unknown): Lean | null {
  return typeof value === "string" && LEANS.includes(value) ? (value as Lean) : null;
}
function strings(value: unknown): string[] {
  return list(value).filter((v): v is string => typeof v === "string");
}
function numbers(value: unknown): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [key, v] of Object.entries(rec(value) ?? {})) if (typeof v === "number") out[key] = v;
  return out;
}

function attempts(value: unknown): Attempt[] {
  return list(value).flatMap((raw) => {
    const a = rec(raw);
    if (!a) return [];
    return [
      {
        attempt: num(a.attempt, 1),
        seconds: num(a.seconds),
        promptTokens: num(a.prompt_tokens),
        outputTokens: num(a.output_tokens),
        ok: a.ok === true,
        error: strOrNull(a.error),
      },
    ];
  });
}

function turn(raw: unknown): HoodTurn | null {
  const t = rec(raw);
  if (!t || typeof t.agent !== "string") return null;
  const said = rec(t.take_or_rebuttal);
  const trace = rec(t.trace) ?? {};
  const ratings: Record<string, Rating> = {};
  for (const [key, v] of Object.entries(rec(said?.ratings) ?? {})) {
    const r = rec(v);
    if (r && typeof r.score === "number") ratings[key] = { reason: str(r.reason), score: r.score };
  }
  return {
    agent: t.agent,
    status: str(t.status, "ok"),
    seconds: num(t.seconds),
    lean: lean(said?.lean),
    ratings,
    modelCalls: list(trace.model_calls).flatMap((m) => {
      const c = rec(m);
      return c
        ? [
            {
              step: num(c.step, 1),
              seconds: num(c.seconds),
              promptTokens: num(c.prompt_tokens),
              outputTokens: num(c.output_tokens),
              toolCallsRequested: num(c.tool_calls_requested),
            },
          ]
        : [];
    }),
    toolCalls: list(trace.tool_calls).flatMap((raw) => {
      const c = rec(raw);
      if (!c || typeof c.tool !== "string") return [];
      return [
        {
          step: num(c.step, 1),
          tool: c.tool,
          arguments: rec(c.arguments) ?? {},
          ok: c.ok === true,
          result: rec(c.result),
          error: strOrNull(c.error),
          seconds: num(c.seconds),
        },
      ];
    }),
    attempts: attempts(trace.attempts),
  };
}

function scoring(raw: unknown): Scoring | null {
  const s = rec(raw);
  const verdict = lean(s?.verdict);
  if (!s || typeof s.score !== "number" || !verdict) return null;
  const leans: Record<string, Lean> = {};
  for (const [name, v] of Object.entries(rec(s.leans) ?? {})) {
    const l = lean(v);
    if (l) leans[name] = l;
  }
  const inputs: Record<string, Record<string, number>> = {};
  for (const [name, v] of Object.entries(rec(s.inputs) ?? {})) inputs[name] = numbers(v);
  return {
    score: s.score,
    verdict,
    verdictLabel: str(s.verdict_label, verdict),
    scoreVerdict: lean(s.score_verdict) ?? verdict,
    inputs,
    notCounted: strings(s.not_counted),
    ratingsCounted: num(s.ratings_counted),
    leans,
    rail: strOrNull(s.rail),
    railNote: strOrNull(s.rail_note),
  };
}

function rules(engine: Raw | null): Rules | null {
  const r = rec(engine?.rules);
  const s = rec(r?.scoring);
  if (!r || !s || typeof s.buy_at !== "number" || typeof s.wait_at !== "number") return null;
  return {
    buyAt: s.buy_at,
    waitAt: s.wait_at,
    weights: numbers(s.weights),
    maxRounds: numOrNull(r.max_rounds),
    maxAttempts: numOrNull(r.max_attempts),
    temperature: numOrNull(r.temperature),
    contextTokens: numOrNull(r.context_tokens),
  };
}

function members(engine: Raw | null): Member[] {
  return list(engine?.agents).flatMap((raw) => {
    const a = rec(raw);
    if (!a || typeof a.name !== "string") return [];
    const rubric: Record<string, string> = {};
    for (const [key, v] of Object.entries(rec(a.rubric) ?? {})) if (typeof v === "string") rubric[key] = v;
    return [
      {
        name: a.name,
        focus: str(a.focus),
        voice: str(a.voice),
        rubric,
        tools: strings(a.tools),
        requiredTools: strings(a.required_tools),
        systemPrompt: str(a.system_prompt),
      },
    ];
  });
}

export function parseHood(data: unknown): Hood | null {
  const d = rec(data);
  if (!d || (d.kind !== "council" && d.kind !== "declined")) return null;
  const intake = rec(d.intake) ?? {};
  const guard = rec(d.guard) ?? {};
  const judge = rec(d.judge);
  const timing = rec(d.timing) ?? {};
  const engine = rec(d.engine);
  const prompts = rec(engine?.prompts);

  return {
    kind: d.kind,
    model: str(d.model, "unknown model"),
    intake: {
      note: str(intake.note),
      isGadget: intake.is_tech_gadget === true,
      category: strOrNull(intake.category),
      seconds: num(intake.seconds),
      attempts: attempts(intake.attempts),
    },
    guard: { triggered: guard.triggered === true, by: strings(guard.by), removed: strings(guard.removed) },
    rounds: list(d.rounds).flatMap((raw) => {
      const r = rec(raw);
      if (!r || typeof r.kind !== "string" || !ROUND_KINDS.includes(r.kind)) return [];
      return [
        {
          number: num(r.number),
          kind: r.kind as RoundKind,
          seconds: num(r.seconds),
          turns: list(r.turns).flatMap((t) => turn(t) ?? []),
        },
      ];
    }),
    judge: judge
      ? {
          seconds: num(judge.seconds),
          fallbackUsed: judge.fallback_used === true,
          attempts: attempts(rec(judge.trace)?.attempts),
        }
      : null,
    totalSeconds: num(timing.total_seconds),
    scoring: scoring(d.scoring),
    rules: rules(engine),
    members: members(engine),
    judgePrompt: strOrNull(prompts?.judge),
  };
}
