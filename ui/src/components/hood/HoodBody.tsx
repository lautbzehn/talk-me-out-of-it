/*
  What Under the hood shows, in two parts: the live trace that plays beside the chat, and the
  rest (the scoring math, the run in numbers, the council's brief) below them. They live in
  their own file so the app loads them after the page itself (UnderTheHood.tsx imports them
  lazily): this is the heaviest part of the page, and it sits well below the first screen.
*/
import { useState, type ReactNode } from "react";
import { CouncilBrief } from "@/components/hood/CouncilBrief";
import { RunFacts } from "@/components/hood/RunFacts";
import { RunTrace } from "@/components/hood/RunTrace";
import { ScoreMath } from "@/components/hood/ScoreMath";
import type { Hood } from "@/lib/hood";
import type { ReplayClock } from "@/lib/replay-clock";
import type { TraceSpan } from "@/lib/run-trace";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<TraceSpan["kind"], string> = {
  check: "Check",
  round: "Round",
  agent: "Turn",
  model: "Model call",
  tool: "Tool call, run by Python",
};

function Part({ id, title, caption, children }: { id: string; title: string; caption: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h3 id={id} className="font-mono text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {title}
        </h3>
        <p className="text-sm text-muted-foreground text-pretty">{caption}</p>
      </header>
      {children}
    </section>
  );
}

/**
  Says what the chosen step took in and gave back. On a phone the trace is pinned above the chat
  with little room to spare, so the empty prompt is left to screen readers there; the region
  stays in the page either way, so a newly chosen step is announced.
*/
function SpanDetails({ span }: { span: TraceSpan | null }) {
  return (
    <div
      aria-live="polite"
      className={cn(
        "shrink-0 overflow-y-auto rounded-card border border-border bg-muted/30 px-4 py-3 max-lg:max-h-36 lg:max-h-64",
        !span && "max-lg:sr-only",
      )}
    >
      {span ? (
        <div className="flex flex-col gap-2.5">
          <p className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">{KIND_LABEL[span.kind]}</span>
            <span className="font-mono text-sm font-semibold text-foreground-strong">
              {span.label}
              {span.attempt && span.attempt > 1 ? ` ×${span.attempt}` : ""}
            </span>
          </p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            {span.info.map((row) => (
              <div key={row.label} className="contents">
                <dt className="font-mono text-xs leading-5 text-muted-foreground">{row.label}</dt>
                <dd className="min-w-0 break-words font-mono text-xs leading-5 text-foreground tabular-nums">{row.value}</dd>
              </div>
            ))}
          </dl>
          {span.note ? <p className="text-sm leading-relaxed text-foreground text-pretty">{span.note}</p> : null}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Choose a step to see what went in and what came out.</p>
      )}
    </div>
  );
}

/** The run, step by step: the trace that plays beside the chat, on the chat's clock. */
export function HoodLive({
  hood,
  spans,
  total,
  clock,
  reduced,
}: {
  hood: Hood;
  spans: TraceSpan[];
  total: number;
  clock: ReplayClock;
  reduced: boolean;
}) {
  const [selected, setSelected] = useState<TraceSpan | null>(null);
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 sm:p-4">
      <RunTrace
        spans={spans}
        total={total}
        model={hood.model}
        clock={clock}
        reduced={reduced}
        selectedId={selected?.id ?? null}
        onSelect={setSelected}
      />
      <SpanDetails span={selected} />
    </div>
  );
}

/** Everything else Under the hood shows, below the chat and the trace. */
export function HoodMore({ hood }: { hood: Hood }) {
  return (
    <div className={cn("grid grid-cols-1 gap-10 px-4 py-6 sm:px-5", hood.scoring && "lg:grid-cols-2 lg:gap-x-12")}>
      {hood.scoring ? (
        <Part
          id="hood-math"
          title="How the verdict was worked out"
          caption="The model judges, the code calculates. Here is the calculation, from the saved ratings."
        >
          <ScoreMath hood={hood} />
        </Part>
      ) : null}

      <div className="flex flex-col gap-10">
        <Part id="hood-facts" title="The run in numbers" caption="Counted from the trace, with the settings the engine saved about itself.">
          <RunFacts hood={hood} />
        </Part>

        {hood.members.length > 0 ? (
          <Part id="hood-brief" title="The council's brief" caption="What each member was told: its role, voice, rubric, tools and full system prompt.">
            <CouncilBrief hood={hood} />
          </Part>
        ) : null}
      </div>
    </div>
  );
}