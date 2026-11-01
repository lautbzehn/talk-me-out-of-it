/*
  The debate: the council's saved transcript played back as a group chat.

  The chat shows beats (lib/playback.ts) one by one: a pause, the typing dots, the message. It
  keeps no time of its own. The shared replay clock does (lib/replay-clock.ts), so Under the
  hood's run trace beside it is always on the same moment. The viewer can pause, skip to the end
  or replay, here or from the trace. Someone who prefers reduced motion gets the whole transcript
  at once with no controls, since there is nothing to play.
*/
import { useEffect, useRef, type ComponentType } from "react";
import { MessagesSquare, Pause, Play, RotateCcw, SkipForward } from "lucide-react";
import { agentStyle } from "@/lib/agents";
import { Divider, Message, Notice } from "@/components/debate/Message";
import { TypingIndicator, TypingStatus } from "@/components/debate/TypingIndicator";
import type { ReplayState } from "@/components/debate/use-replay";
import type { Beat } from "@/lib/playback";
import { cn } from "@/lib/utils";

/** The card surface the verdict, the debate and Under the hood share. */
export const PANEL =
  "rounded-card border border-border bg-card text-card-foreground shadow-[0_24px_64px_-24px_rgba(0,0,0,0.6)]";

/** How far below the viewer's screen the end of the chat can be and still count as "following along". */
const FOLLOW_SLACK_PX = 240;
/** How far above the screen the end of the chat can be before the viewer has clearly moved on. */
const FOLLOW_ABOVE_PX = 120;

/**
  A small pill button with an icon: the debate's controls, and the share buttons.

  `disabled` is announced and drawn as disabled but the button stays focusable and ignores the
  press. A real `disabled` attribute on the button someone just pressed makes the browser drop
  keyboard focus to the page, so a keyboard or screen reader user would lose their place.
*/
export function ControlButton({
  icon: Icon,
  onClick,
  primary = false,
  disabled = false,
  children,
}: {
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;
  onClick: () => void;
  primary?: boolean;
  disabled?: boolean;
  children: string;
}) {
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      aria-disabled={disabled || undefined}
      className={cn(
        "inline-flex h-9 items-center gap-1.5 rounded-full border px-3.5 font-mono text-xs font-medium transition-colors aria-disabled:cursor-wait aria-disabled:opacity-60",
        primary
          ? "border-primary bg-primary text-primary-foreground hover:bg-primary/90"
          : "border-border bg-muted text-foreground hover:border-muted-foreground",
      )}
    >
      <Icon aria-hidden="true" className="size-3.5" />
      {children}
    </button>
  );
}

export interface ReplayControls {
  start: () => void;
  pause: () => void;
  resume: () => void;
  skip: () => void;
  restart: () => void;
}

export function DebateChat({
  beats,
  members,
  rounds,
  state,
  controls,
  reduced,
}: {
  beats: readonly Beat[];
  members: number;
  rounds: number;
  state: ReplayState;
  controls: ReplayControls;
  reduced: boolean;
}) {
  const { start, pause, resume, skip, restart } = controls;
  const sectionRef = useRef<HTMLElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const following = useRef(true);

  // Remember whether the viewer is watching the end of the chat. If they scroll up to reread, or
  // down past it, new messages arrive quietly instead of pulling the page back.
  useEffect(() => {
    const update = () => {
      const end = endRef.current;
      if (!end) return;
      const top = end.getBoundingClientRect().top;
      following.current = top >= -FOLLOW_ABOVE_PX && top <= window.innerHeight + FOLLOW_SLACK_PX;
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  // Keep the newest bubble or the typing dots in view while someone is following along. "nearest"
  // scrolls only when the new end of the chat would be below the screen, and never backwards.
  // The last message arrives in the same update that makes the status "done", so that counts
  // too. Beats shown in bulk (skip to end, a scrub of the trace, reduced motion) never scroll the page.
  useEffect(() => {
    const watching = state.status === "playing" || state.status === "done";
    const end = endRef.current;
    if (!watching || state.instant || !following.current || !end) return;
    // Only ever bring the end up from below. If it is on screen, or above it because the viewer
    // has moved on down the page, leave the page where it is.
    if (end.getBoundingClientRect().top <= window.innerHeight - 24) return;
    end.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [state.status, state.visible, state.typing, state.instant]);

  const typingBeat = state.typing ? beats[state.visible] : undefined;
  const typingAgent = typingBeat && typingBeat.kind !== "divider" ? agentStyle(typingBeat.agent) : null;
  const animate = !state.instant && !reduced;

  // Each control swaps itself for another (Pause becomes Resume, Skip leaves Replay), and a button
  // that disappears takes keyboard focus with it. So after every control, focus lands on the first
  // control that is there now, without scrolling the page to it.
  const controlsRef = useRef<HTMLDivElement>(null);
  const control = (action: () => void) => () => {
    action();
    requestAnimationFrame(() => controlsRef.current?.querySelector("button")?.focus({ preventScroll: true }));
  };

  const onReplay = () => {
    restart();
    sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <section ref={sectionRef} aria-labelledby="debate-title" className={cn(PANEL, "scroll-mt-6")}>
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 border-b border-border px-4 py-4 sm:px-5">
        <div className="flex flex-col gap-1">
          <h2
            id="debate-title"
            className="flex items-center gap-1.5 font-mono text-[11px] font-medium uppercase tracking-wider text-muted-foreground"
          >
            <MessagesSquare aria-hidden="true" className="size-3.5" />
            The debate
          </h2>
          <p className="font-mono text-[13px] text-muted-foreground tabular-nums">
            {members} members · {rounds} rounds
          </p>
        </div>
        {reduced ? null : (
          <div ref={controlsRef} className="flex items-center gap-2">
            {state.status === "done" ? (
              <ControlButton icon={RotateCcw} onClick={control(onReplay)} primary>
                Replay
              </ControlButton>
            ) : (
              <>
                {state.status === "paused" ? (
                  <ControlButton icon={Play} onClick={control(resume)} primary>
                    Resume
                  </ControlButton>
                ) : state.status === "playing" ? (
                  <ControlButton icon={Pause} onClick={control(pause)}>
                    Pause
                  </ControlButton>
                ) : null}
                <ControlButton icon={SkipForward} onClick={control(skip)}>
                  Skip to end
                </ControlButton>
              </>
            )}
          </div>
        )}
      </header>

      <div className="px-4 py-5 sm:px-5">
        {state.status === "idle" ? (
          <div className="flex justify-center py-3">
            <ControlButton icon={Play} onClick={control(start)} primary>
              Watch the debate
            </ControlButton>
          </div>
        ) : null}
        <div
          role="log"
          aria-label="The council's debate"
          aria-live={state.status === "playing" ? "polite" : "off"}
          aria-relevant="additions"
        >
          <ol className="flex flex-col gap-5">
            {beats.slice(0, state.visible).map((beat) =>
              beat.kind === "divider" ? (
                <Divider key={beat.id} beat={beat} animate={animate} />
              ) : beat.kind === "notice" ? (
                <Notice key={beat.id} beat={beat} animate={animate} />
              ) : (
                <Message key={beat.id} beat={beat} animate={animate} />
              ),
            )}
          </ol>
        </div>

        {typingAgent ? (
          <div className="mt-5">
            <TypingIndicator agent={typingAgent} />
          </div>
        ) : null}
        <TypingStatus label={typingAgent && state.status === "playing" ? `${typingAgent.name} is typing` : ""} />
        <div ref={endRef} aria-hidden="true" className="scroll-mb-6" />
      </div>
    </section>
  );
}
