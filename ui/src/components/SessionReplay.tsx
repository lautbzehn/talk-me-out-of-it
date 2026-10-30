/*
  The replay: the debate as a group chat and Under the hood's run trace, side by side and on one
  clock. The chat shows what the council said; the trace shows the engine running under it, each
  member's turn filling while that member's dots show. Pause, skip or replay from either one and
  both follow; scrub the trace and the chat moves with it. Below them, the rest of Under the hood.

  Loads the full transcript the gallery index points to, then builds everything from it: the
  chat's beats (lib/playback.ts), the trace's spans (lib/run-trace.ts) and the timeline that ties
  the two together.
*/
import { useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import { DebateChat, PANEL } from "@/components/Debate";
import { useReplay } from "@/components/debate/use-replay";
import { HoodLivePanel, HoodMorePanel } from "@/components/UnderTheHood";
import type { GallerySession } from "@/lib/gallery";
import { buildBeats, buildTimeline, describeCouncil } from "@/lib/playback";
import { buildSpans } from "@/lib/run-trace";
import { loadTranscript, type Transcript } from "@/lib/transcript";
import { cn } from "@/lib/utils";

type Loaded = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; transcript: Transcript };

export function SessionReplay({ session }: { session: GallerySession }) {
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });

  useEffect(() => {
    let cancelled = false;
    loadTranscript(session.file)
      .then((transcript) => {
        if (!cancelled) setLoaded({ state: "ready", transcript });
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoaded({ state: "error", message: error instanceof Error ? error.message : String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [session.file]);

  if (loaded.state === "ready") return <ReplayStage transcript={loaded.transcript} />;

  return (
    <section aria-label="The debate" className={cn(PANEL, "mx-auto mt-6 max-w-xl p-5")}>
      {loaded.state === "loading" ? (
        <p className="font-mono text-sm text-muted-foreground" role="status">
          Loading the debate…
        </p>
      ) : (
        <p className="text-sm" role="alert">
          {loaded.message}
        </p>
      )}
    </section>
  );
}

function ReplayStage({ transcript }: { transcript: Transcript }) {
  const reduced = useReducedMotion() ?? false;
  const council = transcript.kind === "council";
  const beats = useMemo(() => (council ? buildBeats(transcript) : []), [transcript, council]);
  const { members, rounds } = useMemo(() => describeCouncil(transcript), [transcript]);
  const trace = useMemo(() => (transcript.hood ? buildSpans(transcript.hood) : null), [transcript]);
  const timeline = useMemo(
    () => buildTimeline(beats, new Map((trace?.spans ?? []).map((span) => [span.id, span])), trace?.total ?? 0),
    [beats, trace],
  );
  const { state, clock } = useReplay(timeline, reduced);
  const stageRef = useRef<HTMLDivElement>(null);

  // Start when the replay's top reaches the upper 55% of the screen, so it is not spent (and the
  // page does not start moving) while the viewer is still reading the verdict card. Until then
  // the empty chat offers a "Watch the debate" button, which matters when the session sits at the
  // bottom of the page and cannot scroll that high. (Without IntersectionObserver, start at once.)
  useEffect(() => {
    if (state.status !== "idle") return;
    const stage = stageRef.current;
    if (!stage) return;
    if (typeof IntersectionObserver === "undefined") {
      clock.start();
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) clock.start();
      },
      { rootMargin: "0px 0px -45% 0px" },
    );
    observer.observe(stage);
    return () => observer.disconnect();
  }, [state.status, clock]);

  const controls = useMemo(
    () => ({
      start: () => clock.start(),
      pause: () => clock.pause(),
      resume: () => clock.resume(),
      skip: () => clock.skip(),
      restart: () => clock.restart(),
    }),
    [clock],
  );

  return (
    <>
      <div
        ref={stageRef}
        className={cn("mt-6 grid grid-cols-1 gap-4 lg:gap-6", council ? "lg:grid-cols-2 lg:items-start" : "mx-auto max-w-xl")}
      >
        {council ? (
          <DebateChat beats={beats} members={members} rounds={rounds} state={state} controls={controls} reduced={reduced} />
        ) : null}
        <HoodLivePanel hood={transcript.hood} trace={trace} clock={clock} reduced={reduced} debated={council} />
      </div>
      {transcript.hood ? <HoodMorePanel hood={transcript.hood} className={council ? undefined : "mx-auto max-w-xl"} /> : null}
    </>
  );
}
