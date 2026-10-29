/*
  The open Under the hood panel. It lives in its own file so the app can load it only when a
  viewer opens the panel (UnderTheHood.tsx imports it lazily): most visitors never do, and this
  is the heaviest part of the page.
*/
import { useMemo, useState, type ReactNode } from "react";
import { useReducedMotion } from "motion/react";
import { CouncilBrief } from "@/components/hood/CouncilBrief";
import { RunFacts } from "@/components/hood/RunFacts";
import { RunTrace } from "@/components/hood/RunTrace";
import { ScoreMath } from "@/components/hood/ScoreMath";
import type { Hood } from "@/lib/hood";
import { buildSpans, type TraceSpan } from "@/lib/run-trace";

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

function SpanDetails({ span }: { span: TraceSpan | null }) {
  return (
    <div aria-live="polite" className="rounded-card border border-border bg-muted/30 px-4 py-3">
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

export default function HoodBody({ hood }: { hood: Hood }) {
  const reduced = useReducedMotion() ?? false;
  const { spans, total } = useMemo(() => buildSpans(hood), [hood]);
  const [selected, setSelected] = useState<TraceSpan | null>(null);

  return (
    <div className="flex flex-col gap-10 border-t border-border px-4 py-6 sm:px-5">
      {hood.scoring ? (
        <Part
          id="hood-math"
          title="How the verdict was worked out"
          caption="The model judges, the code calculates. Here is the calculation, from the saved ratings."
        >
          <ScoreMath hood={hood} />
        </Part>
      ) : null}

      <Part
        id="hood-run"
        title="The run, step by step"
        caption="Every model call, tool call and retry, in the order the engine ran them, replayed in about six seconds. Drag to scrub."
      >
        <RunTrace
          spans={spans}
          total={total}
          model={hood.model}
          reduced={reduced}
          selectedId={selected?.id ?? null}
          onSelect={setSelected}
        />
        <SpanDetails span={selected} />
      </Part>

      <Part id="hood-facts" title="The run in numbers" caption="Counted from the trace, with the settings the engine saved about itself.">
        <RunFacts hood={hood} />
      </Part>

      {hood.members.length > 0 ? (
        <Part id="hood-brief" title="The council's brief" caption="What each member was told: its role, voice, rubric, tools and full system prompt.">
          <CouncilBrief hood={hood} />
        </Part>
      ) : null}
    </div>
  );
}
