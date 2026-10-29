/*
  The gallery: one card per saved session. Choosing a card shows its verdict and debate below.

  Adapted from the Feature Grid Spotlight Cards on 21st.dev (pulled/feature-grid-spotlight-cards,
  MIT): the cards sit on hairline rails that run past their edges and meet in the gaps, with a
  crosshair mark on two corners, a warm glow in the top corner, and a light that follows the
  pointer. Phones have no hover, so the light also shows where a finger presses (the tap state
  Dan asked for), and the chosen card keeps a quiet ring and a "Now showing" label.

  Each card is an article with a real heading; the heading holds the button, and the button's
  ::after stretches over the whole card, so the whole card is one tap target while a screen
  reader still finds a heading and a button named after the item.
*/
import type { PointerEvent } from "react";
import { Ban, CalendarClock, CircleCheck, CircleSlash, type LucideIcon } from "lucide-react";
import { VerdictPill } from "@/components/VerdictCard";
import { formatPrice, type GallerySession, type Verdict } from "@/lib/gallery";
import { cn } from "@/lib/utils";

const VERDICT_ICON: Record<Verdict, LucideIcon> = { buy: CircleCheck, wait: CalendarClock, skip: Ban };

/** Corner crosshair, drawn half outside the card edge like a survey mark. */
function CrossDecor({ position }: { position: "top-start" | "bottom-end" }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1"
      strokeLinecap="round"
      className={cn(
        "pointer-events-none absolute z-10 size-3.5 text-muted-foreground",
        position === "top-start" && "left-0 top-0 -translate-x-1/2 -translate-y-1/2",
        position === "bottom-end" && "bottom-0 right-0 translate-x-1/2 translate-y-1/2",
      )}
    >
      <path d="M5 12h14" />
      <path d="M12 5v14" />
    </svg>
  );
}

/** Moves the spotlight to the pointer. Written to CSS variables, so React never re-renders for it. */
function aimSpotlight(event: PointerEvent<HTMLElement>) {
  const rect = event.currentTarget.getBoundingClientRect();
  event.currentTarget.style.setProperty("--mx", `${event.clientX - rect.left}px`);
  event.currentTarget.style.setProperty("--my", `${event.clientY - rect.top}px`);
}

function GalleryCard({
  session,
  selected,
  onSelect,
}: {
  session: GallerySession;
  selected: boolean;
  onSelect: () => void;
}) {
  const Icon = session.verdict ? VERDICT_ICON[session.verdict] : CircleSlash;
  const iconColor = session.verdict ? `var(--verdict-${session.verdict})` : "var(--muted-foreground)";
  const facts = [formatPrice(session.price), `want ${session.want_level} of 10`].join(" · ");

  return (
    <li>
      <article
        onPointerMove={aimSpotlight}
        onPointerDown={aimSpotlight}
        className={cn(
          "group relative isolate flex h-full flex-col gap-4 bg-card px-5 pb-5 pt-6 transition-transform duration-200 active:scale-[0.985]",
          "bg-[radial-gradient(50%_80%_at_25%_0%,var(--warm-glow),transparent)]",
          "has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-4 has-[:focus-visible]:outline-ring has-[:focus-visible]:outline-solid",
          selected && "ring-1 ring-primary/70",
        )}
      >
        {/* The pointer light: on hover with a mouse, while pressed on a phone, and dimly on the chosen card. */}
        <div
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute inset-0 -z-10 opacity-0 transition-opacity duration-300 group-hover:opacity-100 group-active:opacity-100",
            "bg-[radial-gradient(circle_200px_at_var(--mx,30%)_var(--my,0px),color-mix(in_oklab,var(--warm)_14%,transparent),transparent_70%)]",
            selected && "opacity-60",
          )}
        />
        <div aria-hidden="true" className="absolute -inset-y-4 -left-px -z-10 w-px bg-border" />
        <div aria-hidden="true" className="absolute -inset-y-4 -right-px -z-10 w-px bg-border" />
        <div aria-hidden="true" className="absolute -inset-x-4 -top-px -z-10 h-px bg-border" />
        <div aria-hidden="true" className="absolute -inset-x-4 -bottom-px -z-10 h-px bg-border" />
        <CrossDecor position="top-start" />
        <CrossDecor position="bottom-end" />

        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="flex size-10 items-center justify-center rounded-md border border-border bg-muted/30 transition-colors duration-300 group-hover:border-primary/40"
              style={{ color: iconColor }}
            >
              <Icon className="size-5" strokeWidth={1.75} />
            </span>
            {session.verdict ? (
              <VerdictPill verdict={session.verdict} label={session.verdict_label ?? session.verdict} />
            ) : (
              <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-1 font-mono text-xs font-semibold text-muted-foreground">
                Declined
              </span>
            )}
          </div>
          {session.score !== null ? (
            <p className="font-mono text-sm tabular-nums text-foreground">
              {session.score.toFixed(1)}
              <span className="text-muted-foreground"> of 10</span>
            </p>
          ) : null}
        </div>

        <div className="flex flex-col gap-1.5">
          <h3 className="font-mono text-base font-semibold leading-snug text-foreground-strong text-balance">
            <button
              type="button"
              aria-current={selected ? "true" : undefined}
              onClick={onSelect}
              className="text-left after:absolute after:inset-0 after:content-[''] focus-visible:outline-none"
            >
              {session.item}
              <span className="sr-only">, {session.verdict_label ?? "declined"}</span>
            </button>
          </h3>
          <p className="font-mono text-xs text-muted-foreground tabular-nums">{facts}</p>
        </div>

        <p className="text-sm leading-relaxed text-muted-foreground text-pretty">{session.why_featured}</p>

        {selected ? (
          <p className="mt-auto font-mono text-[11px] font-medium uppercase tracking-wider text-primary">Now showing</p>
        ) : null}
      </article>
    </li>
  );
}

export function GalleryGrid({
  sessions,
  selectedId,
  onSelect,
}: {
  sessions: GallerySession[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <ul className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-3">
      {sessions.map((session) => (
        <GalleryCard
          key={session.id}
          session={session}
          selected={session.id === selectedId}
          onSelect={() => onSelect(session.id)}
        />
      ))}
    </ul>
  );
}
