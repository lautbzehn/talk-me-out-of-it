/*
  The run on a time axis: every step of the council, replayed and scrubbable.

  Adapted from Agent Trace on 21st.dev (see ui/pulled/REVIEW.md). Kept: the layout of spans as rows
  under their parents, the bars that fill up to a playhead, statuses that flip from queued to
  running to done, the ruler, the transport (play, a scrub rail you can drag or move with the
  arrow keys, the clock), the screen-reader status per row, and the core trick: one playhead
  time drives everything, and the animation loop writes a CSS variable per row instead of
  re-rendering React each frame. Changed: our colors (each member's bar is its own color, a
  rejected attempt is striped rather than red, since red means Skip here), our icons, no token
  counter or looping, a fixed replay length (the whole run in about six seconds, whatever its
  real length), and choosing a row opens a details panel instead of only seeking.
*/
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";
import { CircleAlert, Cpu, Layers, Pause, Play, ScanSearch, Wrench, type LucideIcon } from "lucide-react";
import { agentStyle } from "@/lib/agents";
import { formatSpanTime, type TraceSpan } from "@/lib/run-trace";
import { cn } from "@/lib/utils";

const REPLAY_MS = 6000;
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

const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);

/** m:ss, for the clock and the ruler (runs are minutes long). */
function clock(ms: number): string {
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
  reduced,
  selectedId,
  onSelect,
}: {
  spans: TraceSpan[];
  total: number;
  model: string;
  reduced: boolean;
  selectedId: string | null;
  onSelect: (span: TraceSpan) => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const railRef = useRef<HTMLDivElement>(null);
  const clockRef = useRef<HTMLSpanElement>(null);
  const statusRef = useRef<HTMLSpanElement>(null);
  const rowsRef = useRef<(RowHandle | null)[]>([]);
  const timeRef = useRef(reduced ? total : 0);
  const playingRef = useRef(false);
  const seekRef = useRef<(ms: number) => void>(() => {});
  const runRef = useRef<() => void>(() => {});
  const haltRef = useRef<() => void>(() => {});
  const [playing, setPlaying] = useState(false);

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

  // The playhead loop. Each frame it moves the playhead and writes, per row, how full the bar is
  // (--p), the state word and the elapsed time: DOM writes only, no React render.
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    rowsRef.current.length = rows.length;
    const speed = total / REPLAY_MS;
    let raf = 0;
    let last = 0;
    let onScreen = true;
    let lastRun = "";

    // `announce` is true when the playhead was moved on purpose (a key, a click, the first paint),
    // false for the animation's own frames.
    const paint = (announce = false) => {
      const t = timeRef.current;
      root.style.setProperty("--t", (t / total).toFixed(5));
      for (const row of rowsRef.current) {
        if (!row) continue;
        const { span } = row;
        const p = span.dur > 0 ? clamp((t - span.start) / span.dur, 0, 1) : t >= span.start ? 1 : 0;
        if (p !== row.lastP) {
          row.el.style.setProperty("--p", p.toFixed(4));
          row.lastP = p;
        }
        const state: RowState = t < span.start ? "queued" : p < 1 ? "running" : span.status === "error" ? "error" : "done";
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
      }
      if (clockRef.current) clockRef.current.textContent = `${clock(t)} / ${clock(total)}`;
      const runState = t >= total ? "complete" : "running";
      if (runState !== lastRun) {
        root.dataset.run = runState;
        if (statusRef.current) statusRef.current.textContent = runState === "complete" ? "Completed" : "Replaying";
        lastRun = runState;
      }
      // The slider's value is only updated when the viewer moved it (or the replay is not
      // playing), never ten times a second during play. During play it used to skip every update,
      // so arrow keys pressed while the replay ran changed the playhead and told a screen reader
      // nothing.
      const rail = playingRef.current && !announce ? null : railRef.current;
      if (rail) {
        rail.setAttribute("aria-valuenow", String(Math.round(t / 1000)));
        rail.setAttribute("aria-valuetext", `${clock(t)} of ${clock(total)}`);
      }
    };

    const frame = (now: number) => {
      raf = 0;
      const dt = Math.min(now - (last || now), 100); // no leap after a hidden tab or a long frame
      last = now;
      timeRef.current += dt * speed;
      if (timeRef.current >= total) {
        timeRef.current = total;
        playingRef.current = false;
        setPlaying(false);
      }
      paint();
      if (playingRef.current) raf = requestAnimationFrame(frame);
    };
    const start = () => {
      if (raf || !playingRef.current || !onScreen || document.hidden) return;
      last = 0;
      raf = requestAnimationFrame(frame);
    };
    const halt = () => {
      cancelAnimationFrame(raf);
      raf = 0;
    };
    runRef.current = start;
    haltRef.current = halt;
    seekRef.current = (ms: number) => {
      timeRef.current = clamp(ms, 0, total);
      last = 0;
      paint(true);
    };

    if (reduced) {
      timeRef.current = total;
      playingRef.current = false;
      setPlaying(false);
    } else {
      playingRef.current = true;
      setPlaying(true);
    }
    paint(true);

    const onVisibility = () => (document.hidden ? halt() : start());
    const observer =
      typeof IntersectionObserver === "undefined"
        ? null
        : new IntersectionObserver(([entry]) => {
            onScreen = entry?.isIntersecting ?? true;
            if (onScreen) start();
            else halt();
          });
    observer?.observe(root);
    document.addEventListener("visibilitychange", onVisibility);
    start();

    return () => {
      halt();
      observer?.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      runRef.current = () => {};
      haltRef.current = () => {};
      seekRef.current = () => {};
    };
  }, [rows, total, reduced]);

  const togglePlay = () => {
    const next = !playingRef.current;
    if (next && timeRef.current >= total) timeRef.current = 0;
    playingRef.current = next;
    setPlaying(next);
    seekRef.current(timeRef.current);
    if (next) runRef.current();
    else haltRef.current();
  };

  const scrubFrom = (clientX: number, el: HTMLElement) => {
    const inset = Number(el.dataset.inset ?? 0);
    const rect = el.getBoundingClientRect();
    const width = rect.width - inset * 2;
    if (width > 0) seekRef.current(((clientX - rect.left - inset) / width) * total);
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
    if (e.key === "Home") seekRef.current(0);
    else if (e.key === "End") seekRef.current(total);
    else if (e.key in delta) seekRef.current(timeRef.current + (delta[e.key] ?? 0));
    else return;
    e.preventDefault();
  };

  // Choosing a row moves the playhead to where that step began and shows its details.
  const selectRow = useCallback(
    (span: LaidSpan) => {
      seekRef.current(span.start);
      onSelect(span);
    },
    [onSelect],
  );

  // Pause the replay while the viewer inspects a step, so the bars stop moving under them.
  useEffect(() => {
    if (selectedId === null || !playingRef.current) return;
    playingRef.current = false;
    setPlaying(false);
    haltRef.current();
  }, [selectedId]);

  // The ruler, gridlines, playhead and scrub surface share one box, lined up with the bars.
  const trackBox = "absolute left-[calc(var(--gutter)+0.75rem)] right-[calc(var(--meta)+0.75rem)]";

  return (
    <div
      ref={rootRef}
      className="group/trace @container/trace w-full overflow-hidden rounded-card border border-border bg-background/40"
    >
      <div className="flex items-center gap-2.5 border-b border-border px-3 py-2.5">
        <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-muted-foreground/40 transition-colors duration-300 group-data-[run=running]/trace:bg-primary" />
        <span className="font-mono text-[13px] font-medium leading-none text-foreground">This run</span>
        <span className="hidden truncate text-xs leading-none text-muted-foreground @sm/trace:inline">
          {model} · {rows.length} steps
        </span>
        <span ref={statusRef} className="ml-auto shrink-0 rounded-full border border-border px-2 py-0.5 font-mono text-[11px] leading-4 text-muted-foreground">
          Completed
        </span>
      </div>

      {/* The name and result columns answer to the trace's own width, not the screen's. On a phone
          the names get the room (short names, a tighter indent) and the bars make do. */}
      <div className="relative [--gutter:144px] [--indent:8px] [--meta:3.25rem] @xs/trace:[--gutter:156px] @md/trace:[--gutter:176px] @md/trace:[--indent:12px] @md/trace:[--meta:9rem]">
        <div
          onPointerDown={onScrubDown}
          onPointerMove={onScrubMove}
          onPointerUp={onScrubUp}
          className="relative h-7 cursor-ew-resize touch-none select-none border-b border-border @max-sm/trace:hidden"
        >
          <div className={cn(trackBox, "inset-y-0")}>
            {ticks.map((t) => (
              <span
                key={t}
                className="absolute top-2 -translate-x-1/2 font-mono text-[10px] leading-none text-muted-foreground tabular-nums"
                style={{ left: `${(t / total) * 100}%` }}
              >
                {clock(t)}
              </span>
            ))}
          </div>
        </div>

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

      <div className="flex items-center gap-3 border-t border-border px-3 py-2">
        <button
          type="button"
          onClick={togglePlay}
          aria-label={playing ? "Pause the replay" : "Replay the run"}
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
          aria-valuenow={Math.round((reduced ? total : 0) / 1000)}
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
