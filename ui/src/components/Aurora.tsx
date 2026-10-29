/*
  The hero's background: three soft blobs of light that drift slowly.

  Adapted from LiquidAurora on 21st.dev (see ui/pulled/REVIEW.md), which arrived as markup only;
  its CSS was never delivered, so this is our own. Each blob is a radial gradient that fades to
  transparent by itself, so no blur filter is needed, and only `transform` animates, which the
  browser can hand to the graphics chip without repainting. The colors are three of the
  council's: Future You violet, the Analyst teal, and Darkmatter's warm primary. Reduced motion
  keeps the blobs still. Purely decorative, so screen readers skip it.
*/
import { cn } from "@/lib/utils";

const BLOBS = [
  {
    place: "-left-[24vmax] -top-[26vmax] h-[52vmax] w-[64vmax]",
    color: "var(--agent-future)",
    strength: "34%",
    duration: "22s",
    delay: "0s",
  },
  {
    place: "-right-[26vmax] -top-[18vmax] h-[48vmax] w-[58vmax]",
    color: "var(--agent-analyst)",
    strength: "30%",
    duration: "26s",
    delay: "-8s",
  },
  {
    place: "left-[10vmax] top-[14vmax] h-[40vmax] w-[52vmax]",
    color: "var(--primary)",
    strength: "22%",
    duration: "30s",
    delay: "-15s",
  },
] as const;

export function Aurora({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none absolute inset-0 -z-10 overflow-hidden [mask-image:linear-gradient(to_bottom,black_45%,transparent)]",
        className,
      )}
    >
      {BLOBS.map((blob) => (
        <div
          key={blob.color}
          className={cn("absolute rounded-full animate-aurora-drift will-change-transform motion-reduce:animate-none", blob.place)}
          style={{
            background: `radial-gradient(closest-side, color-mix(in oklab, ${blob.color} ${blob.strength}, transparent), transparent)`,
            animationDuration: blob.duration,
            animationDelay: blob.delay,
          }}
        />
      ))}
    </div>
  );
}
