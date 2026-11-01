/*
  The run on a time axis: every step of the council, replayed and scrubbable.

  Adapted from Agent Trace on 21st.dev (see ui/pulled/REVIEW.md). Kept: the layout of spans as rows
  under their parents, the bars that fill up to a playhead, statuses that flip from queued to
  running to done, the ruler, the transport (play, a scrub rail you can drag or move with the
  arrow keys, the clock), the screen-reader status per row, and the core trick: one playhead
  time drives everything, and the animation loop writes a CSS variable per row instead of
  re-rendering React each frame. Changed: our colors (each member's bar is its own color, a
  rejected attempt is striped rather than red, since red means Skip here), our icons, no token
  counter or looping, and no clock of its own: the replay clock the chat beside it runs on
  (lib/replay-clock.ts) moves the playhead, so a member's turn fills while their dots show in the
  chat, and scrubbing here moves the chat too. Choosing a row opens a details panel as well as
  seeking. The rows scroll inside the trace, which keeps the step now running in view.
*/
import { memo, useCallback, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";
import { CircleAlert, Cpu, Layers, Pause, Play, ScanSearch, Wrench, type LucideIcon } from "lucide-react";
import { agentStyle } from "@/lib/agents";
import type { ReplayClock, ReplayStatus } from "@/lib/replay-clock";
import { formatSpanTime, type TraceSpan } from "@/lib/run-trace";
import { cn } from "@/lib/utils";

/** After the viewer scrolls the steps themselves, leave them where they put them for this long. */
const HANDS_OFF_MS = 4000;
const TICK_STEPS_MS = [10_000, 15_000, 30_000, 60_000, 120_000, 300_000];

type RowState = "queued" | "running" | "done" | "error";

interface LaidSpan extends TraceSpan {
  depth: number;
  dur: number;
}

interface RowHandle {
  el: HTMLElement;
  dur: HTMLElement | null;
  status: HTMLElement | null;
  span: LaidSpan;
  lastP: number;
  lastState: RowState;
  lastDur: string;
}

const KIND_ICON: Record<Exclude<TraceSpan["kind"], "agent">, LucideIcon> = {
  check: ScanSearch,
  round: Layers,
  model: Cpu,
  tool: Wrench,
};

const STATUS_WORD: Record<RowState, string> = { queued: "queued", running: "running", done: "succeeded", error: "failed" };

const RUN_WORD: Record<ReplayStatus, string> = { idle: "Ready", playing: "Replaying", paused: "Paused", done: "Completed" };

const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);

/** A step has begun once the playhead is past its start. The next turn starts the instant the
    last one ends, so while the chat pauses on a message, the next member is still queued. */
const begun = (span: LaidSpan, t: number) => t > span.start || (span.dur === 0 && t >= span.start);

/** m:ss, for the clock and the ruler (runs are minutes long). */
function clockLabel(ms: number): string {
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Children under their parent, siblings by start time. */
function layout(spans: TraceSpan[]): LaidSpan[] {
  const ids = new Set(spans.map((s) => s.id));
  const children = new Map<string, TraceSpan[]>();
  for (const s of spans) {
    const key = s.parentId && ids.has(s.parentId) ? s.parentId : "";
    children.set(key, [...(children.get(key) ?? []), s]);
  }
  const out: LaidSpan[] = [];
  const walk = (parent: string, depth: number) => {
    for (const kid of [...(children.get(parent) ?? [])].sort((a, b) => a.start - b.start)) {
      out.push({ ...kid, depth, dur: Math.max(0, kid.end - kid.start) });
      walk(kid.id, depth + 1);
    }
  };
  walk("", 0);
  return out;
}

const TraceRow = memo(function TraceRow({
  span,
  index,
  total,
  selected,
  onSelect,
  register,
}: {
  span: LaidSpan;
  index: number;
  total: number;
  selected: boolean;
  onSelect: (span: LaidSpan) => void;
  register: (index: number, handle: RowHandle | null) => void;
}) {
  const member = span.agent ? agentStyle(span.agent) : null;
  const Icon = span.kind === "agent" && member ? member.icon : KIND_ICON[span.kind === "agent" ? "model" : span.kind];
  const settled: RowState = span.status === "error" ? "error" : "done";
  const colored = span.kind === "agent" || span.kind === "model";

  return (
    <div
      ref={(node) =>
        register(
          index,
          node
            ? {
                el: node,
                dur: node.querySelector<HTMLElement>("[data-part='dur']"),
                status: node.querySelector<HTMLElement>("[data-part='status']"),
                span,
                lastP: 1,
                lastState: settled,
                lastDur: formatSpanTime(span.dur),
              }
            : null,
        )
      }
      data-state={settled}
      data-selected={selected ? "true" : undefined}
      style={{ "--p": 1, "--agent": member?.color ?? "var(--muted-foreground)" } as CSSProperties}
      className="group/row relative flex h-8 items-center px-3 transition-colors duration-150 data-[selected=true]:bg-muted/50 data-[state=running]:bg-muted/40"
    >
      {span.depth > 0 ? (
        <div aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-3">
          {Array.from({ length: span.depth }, (_, d) => (
            <span key={d} className="absolute inset-y-0 w-px bg-border" style={{ left: `calc(var(--indent) * ${d} + 9px)` }} />
          ))}
        </div>
      ) : null}

      <span data-part="status" className="sr-only">
        {STATUS_WORD[settled]}
      </span>

      <button
        type="button"
        onClick={() => onSelect(span)}
        aria-current={selected ? "true" : undefined}
        aria-label={`${span.label}, ${span.detail}, ${formatSpanTime(span.dur)}${span.attempt && span.attempt > 1 ? `, attempt ${span.attempt}` : ""}`}
        className="flex w-[var(--gutter)] shrink-0 items-center gap-1.5 rounded-md py-1 pr-2 text-left hover:bg-muted"
        style={{ paddingLeft: `calc(var(--indent) * ${span.depth} + 2px)` }}
      >
        <Icon
          aria-hidden="true"
          className={cn("size-3.5 shrink-0 text-muted-foreground transition-colors duration-200", colored && "group-data-[state=done]/row:text-[color:var(--agent)] group-data-[state=running]/row:text-[color:var(--agent)]")}
        />
        <span className="truncate font-mono text-xs text-foreground transition-colors duration-200 group-data-[state=queued]/row:text-muted-foreground">
          {span.short ? (
            <>
              <span className="@md/trace:hidden">{span.short}</span>
              <span className="hidden @md/trace:inline">{span.label}</span>
            </>
          ) : (
            span.label
          )}
        </span>
        {span.attempt && span.attempt > 1 ? (
          <span className="shrink-0 rounded-md border border-border px-1 font-mono text-[10px] leading-4 text-muted-foreground tabular-nums">
            ×{span.attempt}
          </span>
        ) : null}
      </button>

      <div className="relative h-full flex-1">
        <div
          className="absolute top-1/2 h-2 min-w-[3px] -translate-y-1/2 overflow-hidden rounded-full"
          style={{ left: `${(span.start / total) * 100}%`, width: `${(span.dur / total) * 100}%` }}
        >
          <span aria-hidden="true" className="absolute inset-0 bg-foreground/10" />
          <span
            aria-hidden="true"
            className={cn(
              "absolute inset-0 origin-left",
              span.status === "error"
                ? "bg-[repeating-linear-gradient(135deg,var(--foreground)_0_2px,transparent_2px_5px)] opacity-70"
                : colored
                  ? "bg-[color:var(--agent)]"
                  : span.kind === "tool"
                    ? "bg-foreground/60"
                    : "bg-muted-foreground/60",
            )}
            style={{ transform: "scaleX(var(--p,1))" }}
          />
        </div>
      </div>

      <div className="flex w-[var(--meta)] shrink-0 items-center justify-end gap-1.5 pl-2 transition-opacity duration-200 group-data-[state=queued]/row:opacity-0">
        {span.status === "error" ? <CircleAlert aria-hidden="true" className="size-3.5 shrink-0 text-foreground" /> : null}
        <span className="hidden truncate font-mono text-[11px] text-muted-foreground @md/trace:inline">{span.detail}</span>
        <span data-part="dur" className="shrink-0 font-mono text-[11px] text-foreground/80 tabular-nums">
          {formatSpanTime(span.dur)}
        </span>
      </div>
    </div>
  );
});

export function RunTrace({
  spans,
  total,
  model,
  clock,
  reduced,
  selectedId,
  onSelect,
}: {
  spans: TraceSpan[];
  total: number;
  model: string;
  clock: ReplayClock;
  reduced: boolean;
  selectedId: string | null;
  onSelect: (span: TraceSpan) => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const railRef = useRef<HTMLDivElement>(null);
  const clockRef = useRef<HTMLSpanElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const rowsRef = useRef<(RowHandle | null)[]>([]);
  const [status, setStatus] = useState<ReplayStatus>(clock.status);
  const playing = status === "playing";

  const rows = useMemo(() => layout(spans), [spans]);
  const ticks = useMemo(() => {
    // The bars get about 120 to 200 px, so at most three or four labels fit without touching.
    const step = TICK_STEPS_MS.find((t) => total / t <= 3.5) ?? total / 3;
    const out: number[] = [];
    for (let t = step; t < total; t += step) out.push(t);
    return out;
  }, [total]);

  const registerRow = useCallback((index: number, handle: RowHandle | null) => {
    rowsRef.current[index] = handle;
  }, []);

  // The playhead. Each tick of the shared clock moves it and writes, per row, how full the bar is
  // (--p), the state word and the elapsed time: DOM writes only, no React render.
  useLayoutEffect(() => {
    const root = rootRef.current;
    const box = scrollRef.current;
    if (!root) return;
    rowsRef.current.length = rows.length;
    let lastStatus = "";
    let current = -1;
    let handsOffUntil = 0;

    const paint = () => {
      const t = clock.run;
      root.style.setProperty("--t", (t / total).toFixed(5));
      let latest = -1;
      rowsRef.current.forEach((row, i) => {
        if (!row) return;
        const { span } = row;
        const started = begun(span, t);
        if (started) latest = i;
        const p = span.dur > 0 ? clamp((t - span.start) / span.dur, 0, 1) : started ? 1 : 0;
        if (p !== row.lastP) {
          row.el.style.setProperty("--p", p.toFixed(4));
          row.lastP = p;
        }
        const state: RowState = !started ? "queued" : p < 1 ? "running" : span.status === "error" ? "error" : "done";
        if (state !== row.lastState) {
          row.el.dataset.state = state;
          if (row.status) row.status.textContent = STATUS_WORD[state];
          row.lastState = state;
        }
        const dur = state === "queued" ? "" : formatSpanTime(span.dur * p);
        if (row.dur && dur !== row.lastDur) {
          row.dur.textContent = dur;
          row.lastDur = dur;
        }
      });

      // Keep the step that began last in view inside the trace's own scroll box (never the page),
      // unless the viewer has just scrolled the steps themselves.
      const row = rowsRef.current[latest]?.el;
      if (latest !== current && box && row && performance.now() > handsOffUntil) {
        const top = row.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop;
        if (top < box.scrollTop || top + row.offsetHeight > box.scrollTop + box.clientHeight) {
          const smooth = !clock.jumped && !reduced;
          box.scrollTo({ top: Math.max(0, top - box.clientHeight / 3), behavior: smooth ? "smooth" : "auto" });
        }
      }
      current = latest;

      if (clockRef.current) clockRef.current.textContent = `${clockLabel(t)} / ${clockLabel(total)}`;
      if (clock.status !== lastStatus) {
        root.dataset.run = clock.status === "playing" ? "running" : clock.status;
        lastStatus = clock.status;
      }
      // The slider's value is only updated when the playhead jumped (a key, a drag, a chosen step)
      // or the replay is not playing, never every frame during play. Arrow keys pressed while the
      // replay runs still tell a screen reader where they landed.
      const rail = clock.status === "playing" && !clock.jumped ? null : railRef.current;
      if (rail) {
        rail.setAttribute("aria-valuenow", String(Math.round(t / 1000)));
        rail.setAttribute("aria-valuetext", `${clockLabel(t)} of ${clockLabel(total)}`);
      }
      setStatus(clock.status);
    };

    const handsOff = () => {
      handsOffUntil = performance.now() + HANDS_OFF_MS;
    };
    box?.addEventListener("wheel", handsOff, { passive: true });
    box?.addEventListener("touchstart", handsOff, { passive: true });
    paint();
    const unsubscribe = clock.subscribe(paint);
    return () => {
      unsubscribe();
      box?.removeEventListener("wheel", handsOff);
      box?.removeEventListener("touchstart", handsOff);
    };
  }, [rows, total, clock, reduced]);

  const scrubFrom = (clientX: number, el: HTMLElement) => {
    const inset = Number(el.dataset.inset ?? 0);
    const rect = el.getBoundingClientRect();
    const width = rect.width - inset * 2;
    if (width > 0) clock.seekRun(clamp((clientX - rect.left - inset) / width, 0, 1) * total);
  };
  const onScrubDown = (e: PointerEvent<HTMLElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    scrubFrom(e.clientX, e.currentTarget);
  };
  const onScrubMove = (e: PointerEvent<HTMLElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) scrubFrom(e.clientX, e.currentTarget);
  };
  const onScrubUp = (e: PointerEvent<HTMLElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  };
  const onRailKeyDown = (e: KeyboardEvent) => {
    const step = total / 50;
    const delta: Record<string, number> = { ArrowRight: step, ArrowUp: step, ArrowLeft: -step, ArrowDown: -step, PageUp: step * 10, PageDown: -step * 10 };
    if (e.key === "Home") clock.seekRun(0);
    else if (e.key === "End") clock.seekRun(total);
    else if (e.key in delta) clock.seekRun(clamp(clock.run + (delta[e.key] ?? 0), 0, total));
    else return;
    e.preventDefault();
  };

  // Choosing a row pauses the replay, so the bars and the chat stop moving under the viewer, and
  // moves both to where that step finished: the chat then shows what the step led to.
  const selectRow = useCallback(
    (span: LaidSpan) => {
      clock.pause();
      clock.seekRun(span.end);
      onSelect(span);
    },
    [clock, onSelect],
  );

  // The ruler, gridlines, playhead and scrub surface share one box, lined up with the bars.
  const trackBox = "absolute left-[calc(var(--gutter)+0.75rem)] right-[calc(var(--meta)+0.75rem)]";

  return (
    <div
      ref={rootRef}
      className="group/trace @container/trace flex min-h-0 w-full flex-1 flex-col overflow-hidden rounded-card border border-border bg-background/40"
    >
      <div className="flex shrink-0 items-center gap-2.5 border-b border-border px-3 py-2.5">
        <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-muted-foreground/40 transition-colors duration-300 group-data-[run=running]/trace:bg-primary" />
        <span className="font-mono text-[13px] font-medium leading-none text-foreground">This run</span>
        <span className="hidden truncate text-xs leading-none text-muted-foreground @sm/trace:inline">
          {model} · {rows.length} steps
        </span>
        <span className="ml-auto shrink-0 rounded-full border border-border px-2 py-0.5 font-mono text-[11px] leading-4 text-muted-foreground">
          {RUN_WORD[status]}
        </span>
      </div>

      {/* The name and result columns answer to the trace's own width, not the screen's. On a phone
          the names get the room (short names, a tighter indent) and the bars make do. */}
      <div className="relative flex min-h-0 flex-1 flex-col [--gutter:144px] [--indent:8px] [--meta:3.25rem] @xs/trace:[--gutter:156px] @md/trace:[--gutter:176px] @md/trace:[--indent:12px] @md/trace:[--meta:9rem]">
        <div
          onPointerDown={onScrubDown}
          onPointerMove={onScrubMove}
          onPointerUp={onScrubUp}
          className="relative h-7 shrink-0 cursor-ew-resize touch-none select-none border-b border-border @max-sm/trace:hidden"
        >
          <div className={cn(trackBox, "inset-y-0")}>
            {ticks.map((t) => (
              <span
                key={t}
                className="absolute top-2 -translate-x-1/2 font-mono text-[10px] leading-none text-muted-foreground tabular-nums"
                style={{ left: `${(t / total) * 100}%` }}
              >
                {clockLabel(t)}
              </span>
            ))}
          </div>
        </div>

        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
          <div className="relative py-1">
            <div aria-hidden="true" className={cn(trackBox, "inset-y-0 @max-sm/trace:hidden")}>
              {ticks.map((t) => (
                <span key={t} className="absolute inset-y-0 w-px bg-border/60" style={{ left: `${(t / total) * 100}%` }} />
              ))}
            </div>

            <ol aria-label="Steps in this run" className="relative">
              {rows.map((span, i) => (
                <li key={span.id}>
                  <TraceRow span={span} index={i} total={total} selected={selectedId === span.id} onSelect={selectRow} register={registerRow} />
                </li>
              ))}
            </ol>

            <div aria-hidden="true" className={cn(trackBox, "pointer-events-none inset-y-0")}>
              <div className="relative h-full w-full" style={{ transform: "translateX(calc(var(--t,0) * 100%))" }}>
                <span className="absolute inset-y-0 w-px bg-primary/70" />
                <span className="absolute top-0 size-1.5 -translate-x-[2.5px] rotate-45 bg-primary" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-3 border-t border-border px-3 py-2">
        <button
          type="button"
          onClick={() => clock.toggle()}
          aria-label={playing ? "Pause the replay" : status === "done" ? "Replay from the start" : "Play the replay"}
          className="relative flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-transform duration-150 before:absolute before:-inset-1 before:content-[''] active:scale-[0.97]"
        >
          {playing ? <Pause aria-hidden="true" className="size-3.5 fill-current" /> : <Play aria-hidden="true" className="size-3.5 translate-x-px fill-current" />}
        </button>
        <div
          ref={railRef}
          role="slider"
          tabIndex={0}
          aria-label="Playhead"
          aria-valuemin={0}
          aria-valuemax={Math.round(total / 1000)}
          aria-valuenow={Math.round(clock.run / 1000)}
          data-inset="6"
          onPointerDown={onScrubDown}
          onPointerMove={onScrubMove}
          onPointerUp={onScrubUp}
          onKeyDown={onRailKeyDown}
          className="relative h-9 flex-1 cursor-ew-resize touch-none select-none rounded-md"
        >
          <div className="absolute inset-x-1.5 top-1/2 h-1 -translate-y-1/2 overflow-hidden rounded-full bg-foreground/10">
            <div aria-hidden="true" className="h-full w-full origin-left bg-primary" style={{ transform: "scaleX(var(--t,0))" }} />
          </div>
          <div aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-1.5 right-1.5">
            <div className="relative h-full w-full" style={{ transform: "translateX(calc(var(--t,0) * 100%))" }}>
              <span className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card bg-primary" />
            </div>
          </div>
        </div>
        <span ref={clockRef} className="w-[6.5rem] shrink-0 text-right font-mono text-[11px] text-muted-foreground tabular-nums" />
      </div>
    </div>
  );
}