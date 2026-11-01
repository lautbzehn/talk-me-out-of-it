/*
  Under the hood: how the code reached the verdict. It is always open and always plays with the
  chat. Two panels, each built only from the saved transcript (components/hood/HoodBody.tsx):

  - Beside the chat, the run step by step: every model call, tool call and retry on a time axis
    (Agent Trace), moving on the chat's own clock, so the step that is running is the one the
    chat is showing. On a desktop it sits to the right of the chat and stays in view as the chat
    grows; on a phone it sits above the chat, pinned to the top of the screen.
  - Below them both: how the verdict was worked out (the ratings, the average, the cut-offs, the
    lean rule), the run in numbers, and the council's brief (each member's role, rubric, tools and
    system prompt).

  The panels' code loads after the page itself. `lazy` and `import()` tell the build to put it in
  its own file, and `Suspense` shows the loading line while that file arrives (from this same
  site, a few kilobytes).
*/
import { lazy, Suspense } from "react";
import { Settings2 } from "lucide-react";
import { PANEL } from "@/components/Debate";
import type { Hood } from "@/lib/hood";
import type { ReplayClock } from "@/lib/replay-clock";
import type { TraceSpan } from "@/lib/run-trace";
import { cn } from "@/lib/utils";

const HoodLive = lazy(() => import("@/components/hood/HoodBody").then((m) => ({ default: m.HoodLive })));
const HoodMore = lazy(() => import("@/components/hood/HoodBody").then((m) => ({ default: m.HoodMore })));

function Loading() {
  return (
    <p className="px-5 py-4 font-mono text-sm text-muted-foreground" role="status">
      Loading the trace…
    </p>
  );
}

function PanelHeader({ id, title, line }: { id: string; title: string; line: string }) {
  return (
    <header className="flex shrink-0 items-center gap-3 border-b border-border px-4 py-3 sm:px-5 lg:py-4">
      <Settings2 aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
      <div className="flex min-w-0 flex-col gap-0.5">
        <h2 id={id} className="font-mono text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {title}
        </h2>
        <p className="truncate text-sm text-foreground sm:whitespace-normal sm:text-pretty">{line}</p>
      </div>
    </header>
  );
}

export function HoodLivePanel({
  hood,
  trace,
  clock,
  reduced,
  debated,
}: {
  hood: Hood | null;
  trace: { spans: TraceSpan[]; total: number } | null;
  clock: ReplayClock;
  reduced: boolean;
  /** False for a purchase the council declined: there is no chat to run under. */
  debated: boolean;
}) {
  return (
    <section
      aria-labelledby="hood-name"
      className={cn(
        PANEL,
        "sticky top-2 z-20 flex max-h-[min(46svh,26rem)] flex-col overflow-hidden max-lg:order-first lg:top-6 lg:max-h-[calc(100svh-3rem)]",
      )}
    >
      <PanelHeader
        id="hood-name"
        title="Under the hood"
        line={debated ? "The engine running under the debate, step by step" : "Every step the engine ran, replayed"}
      />
      {hood && trace ? (
        <Suspense fallback={<Loading />}>
          <HoodLive hood={hood} spans={trace.spans} total={trace.total} clock={clock} reduced={reduced} />
        </Suspense>
      ) : (
        <p className="px-5 py-4 text-sm text-muted-foreground">This session saved no trace.</p>
      )}
    </section>
  );
}

export function HoodMorePanel({ hood, className }: { hood: Hood; className?: string }) {
  return (
    <section aria-labelledby="hood-more-name" className={cn(PANEL, "mt-6", className)}>
      <PanelHeader id="hood-more-name" title="Under the hood: the verdict" line="How the code reached this verdict, and what each member was told" />
      <Suspense fallback={<Loading />}>
        <HoodMore hood={hood} />
      </Suspense>
    </section>
  );
}
