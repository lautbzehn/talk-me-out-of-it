/*
  The things in the chat list: a message bubble, a round divider, and the notice for a member
  who sat out. The bubble's look (rounded corners with one squared corner by the avatar, a quiet
  border, the slide-and-settle entrance) comes from the Chat Messages component on 21st.dev
  (see ui/pulled/REVIEW.md), re-colored per member with our tokens. Every member sits on the left,
  as in a group chat; the name above each bubble is in the member's color.
*/
import { m } from "motion/react";
import { Reply } from "lucide-react";
import { agentStyle } from "@/lib/agents";
import { AgentAvatar } from "@/components/debate/AgentAvatar";
import { LeanBadge } from "@/components/debate/LeanBadge";
import { agentVars, BUBBLE_SURFACE, EASE } from "@/components/debate/shared";
import type { DividerBeat, MessageBeat, NoticeBeat } from "@/lib/playback";
import { cn } from "@/lib/utils";

/** `animate` is false when many things appear at once (skip to end, reduced motion). */
interface EntranceProps {
  animate: boolean;
}

export function Message({ beat, animate }: { beat: MessageBeat } & EntranceProps) {
  const agent = agentStyle(beat.agent);
  return (
    <m.li
      style={agentVars(agent)}
      className="flex gap-2.5"
      initial={animate ? { opacity: 0, y: 12, scale: 0.97, x: -14 } : false}
      animate={{ opacity: 1, y: 0, scale: 1, x: 0 }}
      transition={{ duration: 0.35, ease: EASE }}
    >
      <AgentAvatar agent={agent} className="mt-0.5" />
      <div className="flex min-w-0 flex-1 flex-col items-start sm:pr-8">
        <p className="mb-1 font-mono text-xs font-semibold" style={{ color: agent.color }}>
          {agent.name}
          {beat.writtenByCode ? <span className="ml-2 font-normal text-muted-foreground">written by code</span> : null}
        </p>
        <div className={cn(BUBBLE_SURFACE, "w-fit max-w-full px-3.5 py-2.5", beat.lean && "pb-4")}>
          {beat.replyingTo.length > 0 ? (
            <p className="mb-1.5 flex flex-wrap items-center gap-x-1 font-mono text-[11px] text-foreground">
              <Reply aria-hidden="true" className="size-3 shrink-0" />
              <span className="sr-only">Replying to</span>
              {beat.replyingTo.map((name, i) => (
                <span key={name}>
                  <span style={{ color: agentStyle(name).color }}>{name}</span>
                  {i < beat.replyingTo.length - 1 ? "," : ""}
                </span>
              ))}
            </p>
          ) : null}
          <p className="text-[15px] leading-relaxed text-foreground-strong text-pretty">{beat.text}</p>
        </div>
        {beat.lean ? <LeanBadge lean={beat.lean} from={beat.leanFrom} /> : null}
      </div>
    </m.li>
  );
}

export function Divider({ beat, animate }: { beat: DividerBeat } & EntranceProps) {
  return (
    <m.li
      className="flex flex-col items-center gap-1 text-center"
      initial={animate ? { opacity: 0 } : false}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4, ease: EASE }}
    >
      <div className="flex w-full items-center gap-3">
        <span aria-hidden="true" className="h-px flex-1 bg-border" />
        <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{beat.label}</p>
        <span aria-hidden="true" className="h-px flex-1 bg-border" />
      </div>
      <p className="max-w-[34ch] text-xs text-muted-foreground text-balance">{beat.note}</p>
    </m.li>
  );
}

export function Notice({ beat, animate }: { beat: NoticeBeat } & EntranceProps) {
  const agent = agentStyle(beat.agent);
  return (
    <m.li
      style={agentVars(agent)}
      className="flex items-center justify-center gap-2 text-center text-xs text-muted-foreground"
      initial={animate ? { opacity: 0, y: 6 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: EASE }}
    >
      <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full" style={{ background: agent.color }} />
      <span className="text-pretty">{beat.text}</span>
    </m.li>
  );
}
