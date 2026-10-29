/*
  The edge badge: a small pill that straddles the bottom edge of a bubble and says where the
  member leans. Adapted from the BubbleReactions pill in the Chat Bubble Reactions component
  on 21st.dev (see ui/pulled/REVIEW.md), rewritten without class-variance-authority.
  When a turn changed the member's lean, the badge says so ("Now leans Skip (was Wait)").
*/
import type { Lean } from "@/lib/transcript";
import { cn } from "@/lib/utils";

const LEAN_LABEL: Record<Lean, string> = { buy: "Buy", wait: "Wait", skip: "Skip" };

export function LeanBadge({ lean, from, className }: { lean: Lean; from: Lean | null; className?: string }) {
  const color = `var(--verdict-${lean})`;
  return (
    <span
      className={cn(
        "relative z-10 -mt-2.5 ml-3 inline-flex w-fit max-w-full flex-wrap items-center gap-x-1.5 gap-y-0.5 rounded-full border bg-background px-2.5 py-1 font-mono text-[11px] leading-none shadow-sm",
        className,
      )}
      style={{ borderColor: `color-mix(in oklab, ${color} 45%, var(--border))` }}
    >
      <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full" style={{ background: color }} />
      <span className="text-muted-foreground">{from ? "Now leans" : "Leans"}</span>
      <span className="font-semibold" style={{ color }}>
        {LEAN_LABEL[lean]}
      </span>
      {from ? <span className="text-muted-foreground">(was {LEAN_LABEL[from]})</span> : null}
    </span>
  );
}
