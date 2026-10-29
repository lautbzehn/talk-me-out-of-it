/*
  The typing indicator: the member's avatar and three dots that rise in turn, with "X is typing"
  beside them. Adapted from the Typing Indicator on 21st.dev (see ui/pulled/REVIEW.md): the
  rounded dots bubble, the label, and above all its screen-reader behavior. The dots are
  decoration (aria-hidden); a separate polite status region says who is typing, but only after
  the dots have been up for 700 ms, so a flicker is never announced. The dots are plain CSS
  (index.css, --animate-typing-dot), which costs no JavaScript per frame.
*/
import { useEffect, useState } from "react";
import { m } from "motion/react";
import type { AgentStyle } from "@/lib/agents";
import { AgentAvatar } from "@/components/debate/AgentAvatar";
import { agentVars, BUBBLE_SURFACE, EASE } from "@/components/debate/shared";
import { cn } from "@/lib/utils";

const ANNOUNCE_AFTER_MS = 700;

export function TypingIndicator({ agent }: { agent: AgentStyle }) {
  return (
    <m.div
      aria-hidden="true"
      style={agentVars(agent)}
      className="flex items-center gap-2.5"
      initial={{ opacity: 0, scale: 0.9, y: 6 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.2, ease: EASE }}
    >
      <AgentAvatar agent={agent} />
      <span className={cn(BUBBLE_SURFACE, "inline-flex h-9 items-center gap-1 px-3.5")}>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="block size-2 rounded-full bg-foreground-strong animate-typing-dot motion-reduce:animate-none"
            style={{ animationDelay: `${i * 0.16}s` }}
          />
        ))}
      </span>
      <span className="truncate font-mono text-[11px] text-muted-foreground">{agent.name} is typing</span>
    </m.div>
  );
}

/**
  Always mounted, so a screen reader sees the text change inside one live region (a region that
  is created with its text already in it is often not announced). `label` is empty when no one
  is typing.
*/
export function TypingStatus({ label }: { label: string }) {
  const [announced, setAnnounced] = useState(label);
  useEffect(() => {
    const timer = setTimeout(() => setAnnounced(label), ANNOUNCE_AFTER_MS);
    return () => clearTimeout(timer);
  }, [label]);
  return (
    <span role="status" aria-live="polite" aria-atomic="true" className="sr-only">
      {announced}
    </span>
  );
}
