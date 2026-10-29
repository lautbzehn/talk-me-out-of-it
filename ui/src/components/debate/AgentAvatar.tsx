/*
  A member's avatar: a small gradient orb in the member's color with a Lucide icon on it.
  The idea comes from the User Presence Avatar on 21st.dev (see ui/pulled/REVIEW.md), whose
  photos we replace with orbs so no image is ever fetched. Decorative: the name sits next to it.

  The size is a prop, not a className, because `cn()` no longer resolves conflicting classes
  (see lib/utils.ts): a caller's "size-10" would sit beside the base "size-8" and CSS order, not
  the caller, would decide which one wins.
*/
import type { AgentStyle } from "@/lib/agents";
import { cn } from "@/lib/utils";

const SIZES = {
  xs: "size-5 [&_svg]:size-3",
  sm: "size-6 [&_svg]:size-3.5",
  md: "size-8",
  lg: "size-10",
} as const;

export function AgentAvatar({
  agent,
  size = "md",
  className,
}: {
  agent: AgentStyle;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  const Icon = agent.icon;
  return (
    <span
      aria-hidden="true"
      className={cn("flex shrink-0 items-center justify-center rounded-full text-background", SIZES[size], className)}
      style={{
        background: `radial-gradient(circle at 30% 24%, color-mix(in oklab, ${agent.color} 55%, white), ${agent.color} 52%, color-mix(in oklab, ${agent.color} 62%, black))`,
        boxShadow: `0 0 18px -6px ${agent.color}`,
      }}
    >
      <Icon className="size-4" strokeWidth={2.25} />
    </span>
  );
}
