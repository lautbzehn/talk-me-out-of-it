import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import { ArrowUp } from "lucide-react";
import { Debate } from "@/components/Debate";
import { GalleryGrid } from "@/components/GalleryGrid";
import { Hero } from "@/components/Hero";
import { UnderTheHood } from "@/components/UnderTheHood";
import { VerdictCard } from "@/components/VerdictCard";
import { ShareBar } from "@/components/ShareBar";
import { loadGalleryIndex, type GalleryIndex } from "@/lib/gallery";
import { pageTitle, SITE_TITLE } from "@/lib/page-text";
import { HOME_PATH, sessionIdFromPath, sessionPath } from "@/lib/route";
import { RELEASE_DATE, VERSION } from "@/version";

type Loaded = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; index: GalleryIndex };

export default function App() {
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  // The session the address names (/s/<id>), or null on the home page, where the first one shows.
  const [selectedId, setSelectedId] = useState<string | null>(() => sessionIdFromPath(window.location.pathname));
  const [missingId, setMissingId] = useState<string | null>(null);
  const reduced = useReducedMotion() ?? false;
  const sessionRef = useRef<HTMLElement>(null);
  const arrivedByLink = useRef(selectedId !== null);

  // Back and forward move between addresses this page pushed; follow them.
  useEffect(() => {
    const onPopState = () => setSelectedId(sessionIdFromPath(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadGalleryIndex()
      .then((index) => {
        if (!cancelled) setLoaded({ state: "ready", index });
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoaded({ state: "error", message: error instanceof Error ? error.message : String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const sessions = loaded.state === "ready" ? loaded.index.sessions : [];
  const routed = selectedId === null ? undefined : sessions.find((s) => s.id === selectedId);
  const selected = routed ?? sessions[0];

  // A link to a session that is no longer in the gallery: say so, and go back to the home address.
  useEffect(() => {
    if (loaded.state !== "ready" || selectedId === null || routed) return;
    setMissingId(selectedId);
    setSelectedId(null);
    window.history.replaceState(null, "", HOME_PATH);
    requestAnimationFrame(() => document.getElementById("gallery")?.scrollIntoView({ behavior: "instant", block: "start" }));
  }, [loaded.state, selectedId, routed]);

  // Arriving by a session link: go straight to its verdict, without the glide.
  useEffect(() => {
    if (loaded.state !== "ready" || !arrivedByLink.current || !routed) return;
    arrivedByLink.current = false;
    requestAnimationFrame(() => sessionRef.current?.scrollIntoView({ behavior: "instant", block: "start" }));
  }, [loaded.state, routed]);

  // The tab (and the browser's history list) names the session the address names.
  useEffect(() => {
    document.title = routed ? pageTitle(routed) : SITE_TITLE;
  }, [routed]);

  // Choosing a card gives it its own address, brings its verdict into view and moves keyboard focus
  // there, so a keyboard or screen reader user lands on what they chose instead of staying in the grid.
  const choose = (id: string) => {
    if (id !== selectedId) window.history.pushState(null, "", sessionPath(id));
    setSelectedId(id);
    setMissingId(null);
    requestAnimationFrame(() => {
      const section = sessionRef.current;
      if (!section) return;
      section.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      section.focus({ preventScroll: true });
    });
  };

  return (
    <div className="flex min-h-full flex-col">
      <Hero />

      <main className="flex-1">
        <section
          id="gallery"
          aria-labelledby="gallery-title"
          className="mx-auto w-full max-w-5xl scroll-mt-6 overflow-x-clip px-4 pb-16 pt-6 sm:px-6"
        >
          <div className="mb-10 flex flex-col items-center gap-3 text-center">
            <p className="rounded-full border border-border bg-card/70 px-4 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              The gallery
            </p>
            <h2 id="gallery-title" className="font-mono text-2xl font-semibold tracking-tight text-foreground-strong sm:text-3xl">
              Pick a purchase
            </h2>
            {loaded.state === "ready" ? (
              <p className="max-w-[48ch] text-base leading-relaxed text-muted-foreground text-pretty">
                {loaded.index.count} purchases put to the council, saved as they ran on a free model on one Mac. Nothing
                here is live: pick one to see the verdict, then watch the argument play back.
              </p>
            ) : null}
          </div>

          {loaded.state === "loading" ? (
            <p className="text-center text-sm text-muted-foreground" role="status">
              Loading the gallery…
            </p>
          ) : null}

          {loaded.state === "error" ? (
            <p className="rounded-card border border-skip/40 bg-skip/10 px-4 py-3 text-sm" role="alert">
              {loaded.message}
            </p>
          ) : null}

          {missingId ? (
            <p className="mb-8 rounded-card border border-border bg-muted/40 px-4 py-3 text-center text-sm text-foreground" role="status">
              That link points to a session that is not in the gallery any more. Here is the gallery instead.
            </p>
          ) : null}

          {loaded.state === "ready" && selected ? (
            <GalleryGrid sessions={sessions} selectedId={selected.id} onSelect={choose} />
          ) : null}
        </section>

        {selected ? (
          <section
            id="session"
            ref={sessionRef}
            tabIndex={-1}
            aria-label={`The verdict and debate for ${selected.item}`}
            className="mx-auto w-full max-w-xl scroll-mt-6 px-4 pb-10 focus:outline-none sm:px-6"
          >
            <VerdictCard key={selected.id} session={selected} />
            <ShareBar key={`share-${selected.id}`} session={selected} />
            {selected.kind === "council" ? <Debate key={`debate-${selected.id}`} session={selected} /> : null}
            <UnderTheHood key={`hood-${selected.id}`} session={selected} />
            <a
              href="#gallery"
              className="mt-4.5 inline-flex items-center gap-1.5 py-1.5 font-mono text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowUp aria-hidden="true" className="size-3.5" />
              Back to the gallery
            </a>
          </section>
        ) : null}
      </main>

      <footer className="mx-auto w-full max-w-xl px-4 pb-8 text-xs text-muted-foreground sm:px-6">
        <p>
          v{VERSION} · {RELEASE_DATE} · A decision helper, not financial advice. Nothing here buys anything or
          connects to a store.
        </p>
      </footer>
    </div>
  );
}
