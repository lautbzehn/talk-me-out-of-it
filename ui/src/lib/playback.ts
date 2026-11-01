/*
  Turns a transcript into the list of things the group chat shows, in order, and says how long
  each one takes to arrive.

  The transcript drives everything: the order is the order of the turns, the words are the
  words the agents wrote, and the typing time of each message is scaled from the seconds the
  model really took. The only text this file adds is the fixed labels on round dividers and the
  notice for a member who sat out; none of it is a number or a claim about the purchase.
*/
import { agentStyle, JUDGE } from "@/lib/agents";
import type { Lean, RoundKind, Transcript } from "@/lib/transcript";

export interface DividerBeat {
  kind: "divider";
  id: string;
  label: string;
  note: string;
}

export interface MessageBeat {
  kind: "message";
  id: string;
  agent: string;
  text: string;
  replyingTo: string[];
  /** The lean shown on the bubble's edge. The Judge has none: code computes the verdict. */
  lean: Lean | null;
  /** Set only when this turn changed the member's lean. */
  leanFrom: Lean | null;
  /** True for a Judge summary that code wrote because the Judge's own answer failed its checks. */
  writtenByCode: boolean;
  seconds: number;
}

/** A member whose every attempt was rejected. The engine let the council go on without them. */
export interface NoticeBeat {
  kind: "notice";
  id: string;
  agent: string;
  text: string;
  seconds: number;
}

export type Beat = DividerBeat | MessageBeat | NoticeBeat;

const ROUND_LABELS: Record<RoundKind, { name: string; note: string }> = {
  opening: { name: "Opening", note: "Each member gives a first take." },
  rebuttal: { name: "Rebuttal", note: "They answer each other and may change their minds." },
  tiebreak: { name: "Tiebreak", note: "The council was still split, so it went one more round." },
};

/**
  Takes sometimes arrive with a paragraph break or a trailing newline (about 5% of the Analyst's
  and the Hunter's). The chat bubble is one paragraph, so any run of whitespace that holds a
  line break becomes a single space. The engine leaves the model's text alone; the UI tidies it.
*/
export function tidy(text: string): string {
  return text.replace(/\s*\n\s*/g, " ").trim();
}

export function buildBeats(transcript: Transcript): Beat[] {
  const beats: Beat[] = [];

  for (const round of transcript.rounds) {
    const label = ROUND_LABELS[round.kind];
    beats.push({
      kind: "divider",
      id: `round-${round.number}`,
      label: `Round ${round.number} · ${label.name}`,
      note: label.note,
    });

    for (const turn of round.turns) {
      const id = `round-${round.number}-${turn.agent}`;
      const said = turn.take_or_rebuttal;
      const words = said ? (said.take ?? said.response ?? "") : "";

      if (turn.status !== "ok" || !said || tidy(words) === "") {
        beats.push({
          kind: "notice",
          id,
          agent: turn.agent,
          text: `${turn.agent} could not give a valid answer and sat out.`,
          seconds: turn.seconds,
        });
        continue;
      }

      const from = turn.changes?.lean.from ?? null;
      beats.push({
        kind: "message",
        id,
        agent: turn.agent,
        text: tidy(words),
        replyingTo: said.responding_to ?? [],
        lean: said.lean,
        leanFrom: from !== null && from !== said.lean ? from : null,
        writtenByCode: false,
        seconds: turn.seconds,
      });
    }
  }

  if (transcript.judge && transcript.rounds.length > 0) {
    beats.push({
      kind: "divider",
      id: "ruling",
      label: "The ruling",
      note: "Code works out the verdict from the final ratings. The Judge only explains it.",
    });
    beats.push({
      kind: "message",
      id: "judge",
      agent: JUDGE.name,
      text: tidy(transcript.judge.summary),
      replyingTo: [],
      lean: null,
      leanFrom: null,
      writtenByCode: transcript.judge.fallback_used,
      seconds: transcript.judge.seconds,
    });
  }

  return beats;
}

/* Playback speed. All times are in milliseconds. */
const TYPING_MS_PER_REAL_SECOND = 55; // a 37 s model turn shows the dots for about 2 s
const TYPING_MIN_MS = 1000;
const TYPING_MAX_MS = 2800;
const FIRST_BEAT_MS = 1200; // the intake check runs in the trace before the first round opens
const DIVIDER_MS = 450;
const READ_MIN_MS = 600;
const READ_MAX_MS = 1600;
const READ_MS_PER_CHAR = 4;

/** How long the dots show before this message or notice arrives. */
export function typingMs(beat: MessageBeat | NoticeBeat): number {
  return Math.min(TYPING_MAX_MS, Math.max(TYPING_MIN_MS, beat.seconds * TYPING_MS_PER_REAL_SECOND));
}

/** The pause between the previous beat arriving and this one starting (dots, or the divider itself). */
export function pauseBefore(beats: readonly Beat[], index: number): number {
  const previous = beats[index - 1];
  if (!previous) return FIRST_BEAT_MS;
  if (beats[index]?.kind === "divider") return DIVIDER_MS;
  const length = previous.kind === "message" ? previous.text.length : 0;
  return Math.min(READ_MAX_MS, Math.max(READ_MIN_MS, length * READ_MS_PER_CHAR));
}

/* ---- One clock for the chat and the run trace ---------------------------------------------- */

/**
  The chat and Under the hood's run trace play on one clock (lib/replay-clock.ts). The clock
  counts replay time, the milliseconds the chat takes to play back; a timeline turns that into
  run time, the milliseconds into the real run, so the trace's playhead always sits on what the
  chat is showing. While a member's dots show, the playhead crosses that member's turn; while a
  message is being read, it waits. The run times come from the trace (lib/run-trace.ts), whose
  spans for each round, each turn and the Judge have the same ids as the beats.
*/
export interface Segment {
  /** Replay time, in milliseconds. */
  from: number;
  to: number;
  /** Run time at `from` and at `to`. Never goes backwards. */
  runFrom: number;
  runTo: number;
}

export interface Timeline {
  segments: Segment[];
  /** The replay time each beat appears at. */
  reveals: number[];
  /** The replay time each beat's typing dots appear at (null for a divider). */
  typingFrom: (number | null)[];
  /** How long the replay takes. */
  length: number;
  /** How long the real run took. */
  runTotal: number;
}

/** How long the trace plays when there is no chat to keep pace with (a declined purchase). */
const RUN_ONLY_MS = 3000;

export function buildTimeline(
  beats: readonly Beat[],
  spans: ReadonlyMap<string, { start: number; end: number }>,
  runTotal: number,
): Timeline {
  const segments: Segment[] = [];
  const reveals: number[] = [];
  const typingFrom: (number | null)[] = [];
  let t = 0;
  let run = 0;
  const add = (ms: number, runTo: number) => {
    const to = Math.max(run, runTo);
    segments.push({ from: t, to: t + ms, runFrom: run, runTo: to });
    t += ms;
    run = to;
  };

  beats.forEach((beat, i) => {
    // The ruling divider leads into the Judge's turn.
    const span = spans.get(beat.id === "ruling" ? "judge" : beat.id);
    add(pauseBefore(beats, i), span?.start ?? run);
    if (beat.kind === "divider") {
      typingFrom.push(null);
    } else {
      typingFrom.push(t);
      add(typingMs(beat), span?.end ?? run);
    }
    reveals.push(t);
  });

  if (beats.length === 0) add(RUN_ONLY_MS, runTotal);
  // The replay ends where the run ended, including whatever came after the last turn.
  const last = segments.at(-1);
  if (last) last.runTo = Math.max(last.runTo, runTotal);
  return { segments, reveals, typingFrom, length: t, runTotal };
}

/** Where the real run had got to at replay time `t`. */
export function runAt(timeline: Timeline, t: number): number {
  for (const s of timeline.segments) {
    if (t >= s.to) continue;
    if (t <= s.from) return s.runFrom;
    return s.runFrom + ((t - s.from) / (s.to - s.from)) * (s.runTo - s.runFrom);
  }
  return timeline.runTotal;
}

/** The first replay time at which the run reaches `run`: where the chat goes when the trace is scrubbed. */
export function replayAtRun(timeline: Timeline, run: number): number {
  for (const s of timeline.segments) {
    if (s.runTo < run) continue;
    if (run <= s.runFrom) return s.from;
    if (run >= s.runTo) return s.to;
    return s.from + ((run - s.runFrom) / (s.runTo - s.runFrom)) * (s.to - s.from);
  }
  return timeline.length;
}

/** What the chat shows at replay time `t`: how many beats, and whether the next one's dots are up. */
export function chatAt(timeline: Timeline, t: number): { visible: number; typing: boolean } {
  let visible = 0;
  while (visible < timeline.reveals.length && (timeline.reveals[visible] ?? Infinity) <= t) visible += 1;
  const dots = timeline.typingFrom[visible];
  return { visible, typing: dots != null && t >= dots };
}

/** Who and how many: used in the header ("4 members · 3 rounds"). */
export function describeCouncil(transcript: Transcript): { members: number; rounds: number } {
  const names = new Set<string>();
  for (const round of transcript.rounds) for (const turn of round.turns) names.add(agentStyle(turn.agent).name);
  return { members: names.size, rounds: transcript.rounds.length };
}
