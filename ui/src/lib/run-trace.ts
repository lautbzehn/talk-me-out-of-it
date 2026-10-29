/*
  Turns a session's trace into spans on one time axis for the run timeline.

  The engine runs everything one step at a time: the intake check, then each member's turn in
  speaking order, round after round, then the Judge. Inside a turn come the tool steps (a model
  call, then the tools it asked for, run by Python) and then the answer attempts. The transcript
  records how long each step took but not when it started, so the start times here are running
  sums of those durations. That is exact, not a guess: every turn's parts add up to the turn's
  recorded time, and the rounds, intake and Judge add up to the run's total (checked on all 8
  gallery sessions, to within 0.01 s).
*/
import { formatPrice } from "@/lib/gallery";
import type { Attempt, Hood, HoodTurn, ToolCall } from "@/lib/hood";
import type { Lean } from "@/lib/transcript";

export type SpanKind = "check" | "round" | "agent" | "model" | "tool";

export interface InfoRow {
  label: string;
  value: string;
}

export interface TraceSpan {
  id: string;
  label: string;
  /** A shorter name for narrow screens ("Hunter" for "Alternatives Hunter"). */
  short?: string;
  kind: SpanKind;
  /** Milliseconds from the start of the run. */
  start: number;
  end: number;
  status: "ok" | "error";
  parentId?: string;
  /** Council member (or the Judge) the span belongs to, for its color and icon. */
  agent?: string;
  /** Anything above 1 shows a retry chip. */
  attempt?: number;
  /** The short result shown at the end of the row. */
  detail: string;
  /** What the details panel lists when the row is chosen. */
  info: InfoRow[];
  /** A longer line for the details panel: a tool's summary, or why an answer was sent back. */
  note?: string;
}

const LEAN_LABEL: Record<Lean, string> = { buy: "Buy", wait: "Wait", skip: "Skip" };

const SHORT_NAME: Record<string, string> = {
  "The Analyst": "Analyst",
  "Budget Guardian": "Guardian",
  "Alternatives Hunter": "Hunter",
  "The Judge": "Judge",
};

export function groupDigits(n: number): string {
  return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

export function formatSpanTime(ms: number): string {
  if (ms < 1) return "<1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** "video_game" reads as "video game". */
export function humanize(key: string): string {
  return key.replace(/_/g, " ");
}

function tokens(read: number, written: number): InfoRow[] {
  return [
    { label: "Tokens read", value: groupDigits(read) },
    { label: "Tokens written", value: groupDigits(written) },
  ];
}

function toolDetail(call: ToolCall): string {
  if (!call.ok) return "rejected";
  const r = call.result ?? {};
  if (call.tool === "cost_per_use" && typeof r.cost_per_use === "number") return `${formatPrice(r.cost_per_use)} a use`;
  if (call.tool === "estimate_resale" && typeof r.estimated_resale_value === "number") {
    return `about ${formatPrice(r.estimated_resale_value)}`;
  }
  return "done";
}

function argumentValue(value: unknown): string {
  if (typeof value === "string") return humanize(value);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function attemptSpans(attempts: Attempt[], parentId: string, agent: string, start: number, label: string): TraceSpan[] {
  let t = start;
  return attempts.map((a) => {
    const span: TraceSpan = {
      id: `${parentId}-answer-${a.attempt}`,
      label,
      kind: "model",
      start: t,
      end: t + a.seconds * 1000,
      status: a.ok ? "ok" : "error",
      parentId,
      agent,
      attempt: a.attempt,
      detail: a.ok ? "accepted" : "sent back",
      info: [
        { label: "Attempt", value: String(a.attempt) },
        { label: "Took", value: formatSpanTime(a.seconds * 1000) },
        ...tokens(a.promptTokens, a.outputTokens),
      ],
      note: a.ok
        ? "The answer passed every check (the schema, plus the rules code enforces) and was kept."
        : `Sent back to the model with this message: ${a.error ?? "no message recorded"}`,
    };
    t = span.end;
    return span;
  });
}

/** The children of one turn: tool steps, the tools they asked for, then the answer attempts. */
function turnSpans(turn: HoodTurn, parentId: string, start: number): TraceSpan[] {
  const out: TraceSpan[] = [];
  let t = start;
  const steps = [...new Set([...turn.modelCalls.map((m) => m.step), ...turn.toolCalls.map((c) => c.step)])].sort((a, b) => a - b);
  for (const step of steps) {
    for (const call of turn.modelCalls.filter((m) => m.step === step)) {
      out.push({
        id: `${parentId}-step-${step}`,
        label: steps.length > 1 ? `tool step ${step}` : "tool step",
        kind: "model",
        start: t,
        end: t + call.seconds * 1000,
        status: "ok",
        parentId,
        agent: turn.agent,
        detail: `${call.toolCallsRequested} tool call${call.toolCallsRequested === 1 ? "" : "s"}`,
        info: [
          { label: "Took", value: formatSpanTime(call.seconds * 1000) },
          { label: "Tool calls asked for", value: String(call.toolCallsRequested) },
          ...tokens(call.promptTokens, call.outputTokens),
        ],
        note: "The model chose which tools to call and with what inputs. It did no math itself.",
      });
      t += call.seconds * 1000;
    }
    turn.toolCalls
      .filter((c) => c.step === step)
      .forEach((call, i) => {
        const summary = typeof call.result?.summary === "string" ? call.result.summary : null;
        out.push({
          id: `${parentId}-tool-${step}-${i}`,
          label: call.tool,
          kind: "tool",
          start: t,
          end: t + call.seconds * 1000,
          status: call.ok ? "ok" : "error",
          parentId,
          agent: turn.agent,
          detail: toolDetail(call),
          info: [
            ...Object.entries(call.arguments).map(([key, value]) => ({ label: humanize(key), value: argumentValue(value) })),
            { label: "Ran in", value: formatSpanTime(call.seconds * 1000) },
          ],
          note: call.ok
            ? `Python worked this out, not the model. ${summary ?? ""}`.trim()
            : `The tool refused these inputs: ${call.error ?? "no message recorded"}`,
        });
        t += call.seconds * 1000;
      });
  }
  out.push(...attemptSpans(turn.attempts, parentId, turn.agent, t, "answer"));
  return out;
}

export function buildSpans(hood: Hood): { spans: TraceSpan[]; total: number } {
  const spans: TraceSpan[] = [];
  let t = 0;

  const intakeTokens = hood.intake.attempts.reduce(
    (sum, a) => ({ read: sum.read + a.promptTokens, written: sum.written + a.outputTokens }),
    { read: 0, written: 0 },
  );
  spans.push({
    id: "intake",
    label: "Intake check",
    short: "Intake",
    kind: "check",
    start: t,
    end: t + hood.intake.seconds * 1000,
    status: "ok",
    detail: hood.intake.isGadget ? humanize(hood.intake.category ?? "a gadget") : "not a gadget",
    info: [
      { label: "A tech gadget", value: hood.intake.isGadget ? "yes" : "no" },
      { label: "Category", value: hood.intake.category ? humanize(hood.intake.category) : "none" },
      { label: "Took", value: formatSpanTime(hood.intake.seconds * 1000) },
      ...tokens(intakeTokens.read, intakeTokens.written),
    ],
    note: hood.intake.note || undefined,
  });
  t += hood.intake.seconds * 1000;

  for (const round of hood.rounds) {
    const roundId = `round-${round.number}`;
    const roundStart = t;
    const children: TraceSpan[] = [];
    for (const turn of round.turns) {
      const turnId = `${roundId}-${turn.agent}`;
      const turnStart = t;
      const sub = turnSpans(turn, turnId, turnStart);
      const ok = turn.status === "ok";
      const end = Math.max(turnStart + turn.seconds * 1000, sub.at(-1)?.end ?? turnStart);
      children.push({
        id: turnId,
        label: turn.agent,
        short: SHORT_NAME[turn.agent],
        kind: "agent",
        start: turnStart,
        end,
        status: ok ? "ok" : "error",
        parentId: roundId,
        agent: turn.agent,
        detail: ok && turn.lean ? `leans ${LEAN_LABEL[turn.lean]}` : "sat out",
        info: [
          { label: "Took", value: formatSpanTime(end - turnStart) },
          { label: "Lean", value: ok && turn.lean ? LEAN_LABEL[turn.lean] : "none" },
          { label: "Answer attempts", value: String(turn.attempts.length) },
        ],
        note: ok ? undefined : "Every attempt was sent back, so the council went on without this member.",
      });
      // A turn with one clean answer and no tools would only repeat itself one level down.
      if (sub.length > 1 || !ok) children.push(...sub);
      t = end;
    }
    spans.push({
      id: roundId,
      label: `Round ${round.number} · ${round.kind}`,
      short: `Round ${round.number}`,
      kind: "round",
      start: roundStart,
      end: Math.max(t, roundStart + round.seconds * 1000),
      status: "ok",
      detail: `${round.turns.length} turns`,
      info: [
        { label: "Round", value: `${round.number}, ${round.kind}` },
        { label: "Turns", value: String(round.turns.length) },
        { label: "Took", value: formatSpanTime(round.seconds * 1000) },
      ],
    });
    spans.push(...children);
    t = Math.max(t, roundStart + round.seconds * 1000);
  }

  if (hood.judge) {
    const judgeStart = t;
    const sub = attemptSpans(hood.judge.attempts, "judge", "The Judge", judgeStart, "summary");
    const end = Math.max(judgeStart + hood.judge.seconds * 1000, sub.at(-1)?.end ?? judgeStart);
    spans.push({
      id: "judge",
      label: "The Judge",
      short: "Judge",
      kind: "agent",
      start: judgeStart,
      end,
      status: "ok",
      agent: "The Judge",
      detail: hood.judge.fallbackUsed ? "code wrote it" : "explained",
      info: [
        { label: "Took", value: formatSpanTime(end - judgeStart) },
        { label: "Attempts", value: String(hood.judge.attempts.length) },
      ],
      note: hood.judge.fallbackUsed
        ? "Every attempt was sent back, so code wrote a template summary instead."
        : "The Judge explains the verdict code already worked out. It has no verdict or score field to fill in.",
    });
    if (sub.length > 1) spans.push(...sub);
    t = end;
  }

  return { spans, total: Math.max(t, hood.totalSeconds * 1000, 1) };
}
