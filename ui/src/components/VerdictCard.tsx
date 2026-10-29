/*
  The verdict card: the first thing a visitor sees for a session.

  Adapted from the Tweenly Chart KPI card on 21st.dev (pulled/tweenly-chart-kpi, MIT): the
  count-up headline, the pill, and the goal bar. The goal bar became a 1-to-10 scale with the
  Wait and Buy lines where scoring.py puts them. Written against our tokens; nothing copied
  line for line. The sparkline waits for the full-transcript view.
*/
import { useEffect, useRef } from "react";
import { cubicBezier, m, useReducedMotion } from "motion/react";
import { Gavel } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDuration, formatPrice, type GallerySession, type Verdict } from "@/lib/gallery";

/* The scale. Same numbers as BUY_AT and WAIT_AT in scoring.py. */
const SCALE_MIN = 1;
const SCALE_MAX = 10;
const WAIT_AT = 4.5;
const BUY_AT = 5.5;

/* Mirrors RAIL_NOTES in scoring.py, for an index that does not carry rail_note yet. */
const RAIL_NOTES: Record<string, string> = {
  buy_needs_a_buy_lean:
    "The score alone points to Buy, but no member leaned Buy, so the verdict holds at Wait 30 days.",
  skip_needs_a_skip_lean:
    "The score alone points to Skip, but no member leaned Skip, so the verdict holds at Wait 30 days.",
};

const VERDICT_COLOR: Record<Verdict, string> = {
  buy: "var(--verdict-buy)",
  wait: "var(--verdict-wait)",
  skip: "var(--verdict-skip)",
};

const EASE = [0.22, 1, 0.36, 1] as const;
const COUNT_UP_MS = 1100;
const countEase = cubicBezier(...EASE);

/**
  Counts a number up from zero in the DOM without re-rendering React on every frame. A plain frame
  loop on purpose: Motion's `animate()` can tween numbers, but it brings the engine's general
  animation code into the first download (about 6 KB gzipped) to count to one number.
*/
function useCountUp(target: number, decimals: number, reduced: boolean) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reduced) {
      el.textContent = target.toFixed(decimals);
      return;
    }
    let frame = 0;
    let startedAt = -1;
    const tick = (now: number) => {
      if (startedAt < 0) startedAt = now;
      const progress = Math.min(1, (now - startedAt) / COUNT_UP_MS);
      el.textContent = (target * countEase(progress)).toFixed(decimals);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, decimals, reduced]);
  return ref;
}

function percentOnScale(value: number): number {
  const clamped = Math.min(SCALE_MAX, Math.max(SCALE_MIN, value));
  return ((clamped - SCALE_MIN) / (SCALE_MAX - SCALE_MIN)) * 100;
}

function Tick({ at, label }: { at: number; label: string }) {
  return (
    <span
      aria-hidden="true"
      className="absolute -top-4 flex -translate-x-1/2 flex-col items-center"
      style={{ left: `${percentOnScale(at)}%` }}
    >
      <span className="font-mono text-[10px] leading-none text-muted-foreground tabular-nums">{label}</span>
      <span className="mt-0.5 h-3 w-px bg-muted-foreground/70" />
    </span>
  );
}

function Scale({ score, verdict, reduced }: { score: number; verdict: Verdict; reduced: boolean }) {
  const color = VERDICT_COLOR[verdict];
  const fill = `${percentOnScale(score)}%`;
  return (
    <div
      role="img"
      aria-label={`Score ${score.toFixed(1)} out of 10. Below ${WAIT_AT} is Skip, ${WAIT_AT} to ${BUY_AT} is Wait, ${BUY_AT} and above is Buy.`}
      className="pt-5"
    >
      <div className="relative h-2 rounded-full bg-muted">
        <m.div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ background: color }}
          initial={reduced ? false : { width: 0 }}
          animate={{ width: fill }}
          transition={reduced ? { duration: 0 } : { duration: 1.1, ease: EASE }}
        />
        <Tick at={WAIT_AT} label={String(WAIT_AT)} />
        <Tick at={BUY_AT} label={String(BUY_AT)} />
      </div>
      <div className="mt-2 flex font-mono text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        <span style={{ width: `${percentOnScale(WAIT_AT)}%` }}>Skip</span>
        <span className="text-center" style={{ width: `${percentOnScale(BUY_AT) - percentOnScale(WAIT_AT)}%` }}>
          Wait
        </span>
        <span className="flex-1 text-right">Buy</span>
      </div>
    </div>
  );
}

/** The verdict in its color, as a small pill. The gallery cards use it too. */
export function VerdictPill({ verdict, label }: { verdict: Verdict; label: string }) {
  const color = VERDICT_COLOR[verdict];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-xs font-semibold"
      style={{ color, background: `color-mix(in oklab, ${color} 16%, transparent)` }}
    >
      <span aria-hidden="true" className="size-1.5 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

function Header({ session }: { session: GallerySession }) {
  const facts = [
    formatPrice(session.price),
    `want ${session.want_level} of 10`,
    session.current_device ? `replaces ${session.current_device}` : null,
  ].filter(Boolean);
  return (
    <header className="flex flex-col gap-1">
      <p className="flex items-center gap-1.5 font-mono text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        <Gavel aria-hidden="true" className="size-3.5" />
        The council's verdict
      </p>
      <h2 className="font-mono text-xl font-semibold leading-tight text-foreground-strong text-balance">{session.item}</h2>
      <p className="font-mono text-[13px] text-muted-foreground tabular-nums">{facts.join(" · ")}</p>
    </header>
  );
}

function Ruled({ session, reduced }: { session: GallerySession; reduced: boolean }) {
  const score = session.score ?? 0;
  const verdict = session.verdict ?? "wait";
  const countRef = useCountUp(score, 1, reduced);
  const railNote = session.rail ? (session.rail_note ?? RAIL_NOTES[session.rail] ?? null) : null;

  return (
    <>
      <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
        {/* Hidden from screen readers: the number is mid-count while it animates (a reader that
            arrives early hears "0.0"). The score is spoken once, in the scale's label below. */}
        <p aria-hidden="true" className="flex items-baseline gap-1.5">
          <span
            ref={countRef}
            className="font-mono text-5xl font-semibold leading-none tracking-tight text-foreground-strong tabular-nums"
          >
            {reduced ? score.toFixed(1) : "0.0"}
          </span>
          <span className="font-mono text-sm text-muted-foreground">of 10</span>
        </p>
        <m.div
          initial={reduced ? false : { opacity: 0, scale: 0.7, y: 4 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 22, delay: 0.6 }}
          className="pb-1"
        >
          <VerdictPill verdict={verdict} label={session.verdict_label ?? verdict} />
        </m.div>
      </div>

      <Scale score={score} verdict={verdict} reduced={reduced} />

      {session.ruling ? (
        <p className="text-base leading-relaxed text-foreground-strong text-pretty">{session.ruling}</p>
      ) : null}

      {railNote ? (
        <p className="rounded-card border border-border bg-muted/40 px-3 py-2 text-sm leading-relaxed text-foreground">
          <span className="mr-1.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Rule
          </span>
          {railNote}
        </p>
      ) : null}
    </>
  );
}

function Declined({ session }: { session: GallerySession }) {
  return (
    <>
      <p className="font-mono text-2xl font-semibold leading-tight text-foreground-strong">Not a gadget.</p>
      <p className="text-base leading-relaxed text-foreground text-pretty">
        The council only argues about tech. It declined this one politely instead of debating it.
      </p>
      <p className="text-sm text-muted-foreground text-pretty">{session.why_featured}</p>
    </>
  );
}

export function VerdictCard({ session, className }: { session: GallerySession; className?: string }) {
  const reduced = useReducedMotion() ?? false;
  const meta =
    session.kind === "council"
      ? `${session.rounds} rounds · ${formatDuration(session.seconds)} · ${session.model}`
      : `${formatDuration(session.seconds)} · ${session.model}`;

  return (
    <m.article
      initial={reduced ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduced ? { duration: 0 } : { duration: 0.4, ease: EASE }}
      className={cn(
        "flex flex-col gap-5 rounded-card border border-border bg-card p-5 text-card-foreground shadow-[0_24px_64px_-24px_rgba(0,0,0,0.6)] sm:p-6",
        className,
      )}
      aria-label={`Verdict for ${session.item}`}
    >
      <Header session={session} />
      {session.kind === "council" ? <Ruled session={session} reduced={reduced} /> : <Declined session={session} />}
      <footer className="border-t border-border pt-3 font-mono text-xs text-muted-foreground tabular-nums">{meta}</footer>
    </m.article>
  );
}
