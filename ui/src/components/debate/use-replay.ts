/*
  The chat's view of the shared replay clock (lib/replay-clock.ts). The clock ticks every frame;
  this hook turns it into the few things the chat draws (how many beats are showing, whether the
  dots are up, the play state) and re-renders only when one of those changes.
*/
import { useEffect, useMemo, useState } from "react";
import type { Timeline } from "@/lib/playback";
import { ReplayClock, type ReplayStatus } from "@/lib/replay-clock";

export type { ReplayStatus };

export interface ReplayState {
  status: ReplayStatus;
  /** How many beats are showing. */
  visible: number;
  /** True while the dots for beats[visible] are showing. */
  typing: boolean;
  /** True when the last change came from a jump (skip, scrub), so new beats appear without an entrance. */
  instant: boolean;
}

function read(clock: ReplayClock, previous: ReplayState | null): ReplayState {
  const { visible, typing } = clock.chat;
  if (!previous || previous.visible !== visible || previous.typing !== typing) {
    return { status: clock.status, visible, typing, instant: clock.jumped };
  }
  return previous.status === clock.status ? previous : { ...previous, status: clock.status };
}

export function useReplay(timeline: Timeline, reduced: boolean) {
  // One clock per timeline, which is one per session. `reduced` is read only at the start; a
  // later change is handled below.
  const clock = useMemo(() => new ReplayClock(timeline, reduced), [timeline]);
  const [state, setState] = useState(() => read(clock, null));

  useEffect(() => {
    clock.attach();
    const update = () => setState((previous) => read(clock, previous));
    update();
    const unsubscribe = clock.subscribe(update);
    return () => {
      unsubscribe();
      clock.detach();
    };
  }, [clock]);

  // The viewer prefers reduced motion (now, or they changed the setting while the page was open).
  useEffect(() => {
    if (reduced) clock.skip();
  }, [reduced, clock]);

  return { state, clock };
}
