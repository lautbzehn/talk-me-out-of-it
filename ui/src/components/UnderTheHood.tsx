/*
  Under the hood: the third layer, after the verdict and the debate. Closed until the viewer asks,
  because most people want the verdict and the argument, and the people who want this want all
  of it. Four parts, each built only from the saved transcript (components/hood/HoodBody.tsx):

  1. How the verdict was worked out: the ratings, the average, the cut-offs, the lean rule.
  2. The run, step by step: every model call, tool call and retry on a time axis (Agent Trace).
  3. The run in numbers: calls, retries, tokens, time, settings, the injection guard.
  4. The council's brief: each member's role, rubric, tools and system prompt.

  The panel's code is loaded only when it is first opened. `lazy` and `import()` tell the build to
  put it in its own file, and `Suspense` shows the loading line while that file arrives (from this
  same site, a few kilobytes).
*/
import { lazy, Suspense, useEffect, useState } from "react";
import { ChevronDown, Settings2 } from "lucide-react";
import { PANEL } from "@/components/Debate";
import type { GallerySession } from "@/lib/gallery";
import type { Hood } from "@/lib/hood";
import { loadTranscript } from "@/lib/transcript";
import { cn } from "@/lib/utils";

const HoodBody = lazy(() => import("@/components/hood/HoodBody"));

function Loading() {
  return (
    <p className="border-t border-border px-5 py-4 font-mono text-sm text-muted-foreground" role="status">
      Loading the trace…
    </p>
  );
}

type Loaded = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; hood: Hood | null };

export function UnderTheHood({ session }: { session: GallerySession }) {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });

  // The transcript is already in memory from the debate (loadTranscript caches it), so this is
  // instant; it only waits until the panel is opened.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    loadTranscript(session.file)
      .then((transcript) => {
        if (!cancelled) setLoaded({ state: "ready", hood: transcript.hood });
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoaded({ state: "error", message: error instanceof Error ? error.message : String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [open, session.file]);

  return (
    // The region is named by the short title only; the heading keeps the subtitle too, but a
    // landmark list that read the whole subtitle aloud for every region would be long.
    <section aria-labelledby="hood-name" className={cn(PANEL, "mt-6")}>
      <h2 id="hood-title">
        <button
          type="button"
          aria-expanded={open}
          aria-controls="hood-body"
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center gap-3 rounded-card px-4 py-4 text-left transition-colors hover:bg-muted/30 sm:px-5"
        >
          <Settings2 aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
          <span className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span id="hood-name" className="font-mono text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Under the hood
            </span>
            <span className="text-sm text-foreground text-pretty">How the code reached this verdict, step by step</span>
          </span>
          <ChevronDown
            aria-hidden="true"
            className={cn("size-4 shrink-0 text-muted-foreground transition-transform duration-200", open && "rotate-180")}
          />
        </button>
      </h2>
      {open ? (
        <div id="hood-body">
          {loaded.state === "loading" ? (
            <Loading />
          ) : loaded.state === "error" ? (
            <p className="border-t border-border px-5 py-4 text-sm" role="alert">
              {loaded.message}
            </p>
          ) : loaded.hood ? (
            <Suspense fallback={<Loading />}>
              <HoodBody hood={loaded.hood} />
            </Suspense>
          ) : (
            <p className="border-t border-border px-5 py-4 text-sm text-muted-foreground">This session saved no trace.</p>
          )}
        </div>
      ) : null}
    </section>
  );
}
