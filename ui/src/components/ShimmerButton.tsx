/*
  The main call to action: a pill with a sheen that sweeps across it every few seconds and a
  soft light that follows the pointer.

  Adapted from the Klyv Shimmer Button on 21st.dev (pulled/klyv-shimmer-button, MIT). Its theme
  file (the sweep keyframes, the shadow and color tokens) was not delivered, so the sweep lives in
  index.css (--animate-shimmer-sweep) and the colors are Darkmatter's primary. Kept from the
  original: both effects are one clipped span each, so the label stays crisp and selectable, and
  the pointer light is written to CSS custom properties on the element instead of React state (a
  pointer move fires more often than a frame, and only the compositor needs the value).

  It is a link, not a button: it takes the viewer somewhere on the page, and a link works with
  the keyboard, middle-click and no JavaScript. Reduced motion hides the sweep.
*/
import { useRef, type PointerEvent, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function ShimmerButton({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  const ref = useRef<HTMLAnchorElement>(null);

  const onPointerMove = (event: PointerEvent<HTMLAnchorElement>) => {
    const node = ref.current;
    if (!node) return;
    const rect = node.getBoundingClientRect();
    node.style.setProperty("--glow-x", `${event.clientX - rect.left}px`);
    node.style.setProperty("--glow-y", `${event.clientY - rect.top}px`);
    node.style.setProperty("--glow-opacity", "1");
  };

  return (
    <a
      ref={ref}
      href={href}
      onPointerMove={onPointerMove}
      onPointerLeave={() => ref.current?.style.setProperty("--glow-opacity", "0")}
      className={cn(
        "group/shimmer relative isolate inline-flex h-12 shrink-0 items-center justify-center gap-2 overflow-hidden rounded-full px-6",
        "bg-primary font-mono text-sm font-semibold text-primary-foreground transition-[background-color,transform] duration-200",
        "shadow-[0_10px_30px_-10px_color-mix(in_oklab,var(--primary)_70%,transparent)] hover:bg-[color:color-mix(in_oklab,var(--primary)_88%,white)] active:scale-[0.98]",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -z-10 size-36 -translate-x-1/2 -translate-y-1/2 rounded-full opacity-[var(--glow-opacity,0)] blur-2xl transition-opacity duration-500"
        style={{
          left: "var(--glow-x, 50%)",
          top: "var(--glow-y, 50%)",
          background: "radial-gradient(circle, rgba(255,255,255,0.55) 0%, transparent 70%)",
        }}
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 left-0 -z-10 w-1/3 bg-white/55 blur-[6px] animate-shimmer-sweep motion-reduce:hidden"
      />
      <span className="relative inline-flex items-center gap-2">{children}</span>
    </a>
  );
}
