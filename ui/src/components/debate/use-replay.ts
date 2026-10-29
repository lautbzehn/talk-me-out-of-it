/*
  The replay clock. It walks the list of beats one at a time: a pause, then the typing dots, then
  the message arrives. All the timing comes from lib/playback.ts, which scales it from the
  seconds recorded in the transcript. This hook only keeps the state and the timers.

  A "reducer" is a function that takes the current state and an action and returns the next
  state. Every change to the replay goes through one, so the states can't drift apart (it is
  impossible to be "done" with beats still hidden, for example).

  idle    waiting until the chat scrolls into view
  playing a timer is running
  paused  the viewer paused; nothing is scheduled
  done    everything is showing
*/
import { useCallback, useEffect, useReducer } from "react";
import { pauseBefore, typingMs, type Beat } from "@/lib/playback";

export type ReplayStatus = "idle" | "playing" | "paused" | "done";

export interface ReplayState {
  status: ReplayStatus;
  /** How many beats are showing. */
  visible: number;
  /** True while the dots for beats[visible] are showing. */
  typing: boolean;
  /** True once beats were shown in bulk, so they should appear without an entrance. */
  instant: boolean;
}

type Action =
  | { type: "start" }
  | { type: "pause" }
  | { type: "resume" }
  | { type: "typing" }
  | { type: "reveal"; total: number }
  | { type: "skip"; total: number }
  | { type: "restart" };

function reducer(state: ReplayState, action: Action): ReplayState {
  switch (action.type) {
    case "start":
      return state.status === "idle" ? { ...state, status: "playing" } : state;
    case "pause":
      return state.status === "idle" || state.status === "playing" ? { ...state, status: "paused", typing: false } : state;
    case "resume":
      return state.status === "paused" ? { ...state, status: "playing" } : state;
    case "typing":
      return state.status === "playing" ? { ...state, typing: true } : state;
    case "reveal": {
      if (state.status !== "playing") return state;
      const visible = state.visible + 1;
      return { ...state, visible, typing: false, status: visible >= action.total ? "done" : "playing" };
    }
    case "skip":
      return { status: "done", visible: action.total, typing: false, instant: true };
    case "restart":
      return { status: "playing", visible: 0, typing: false, instant: false };
  }
}

function initialState(total: number, reduced: boolean): ReplayState {
  if (reduced || total === 0) return { status: "done", visible: total, typing: false, instant: true };
  return { status: "idle", visible: 0, typing: false, instant: false };
}

export function useReplay(beats: readonly Beat[], reduced: boolean) {
  const total = beats.length;
  const [state, dispatch] = useReducer(reducer, undefined, () => initialState(total, reduced));

  // The viewer prefers reduced motion (now, or they changed the setting while the page was open).
  useEffect(() => {
    if (reduced) dispatch({ type: "skip", total });
  }, [reduced, total]);

  // The timer. Each run schedules exactly one step, and changing state cancels it and schedules the next.
  const { status, visible, typing } = state;
  useEffect(() => {
    if (status !== "playing") return;
    const next = beats[visible];
    if (!next) return;

    if (typing) {
      if (next.kind === "divider") return;
      const timer = setTimeout(() => dispatch({ type: "reveal", total }), typingMs(next));
      return () => clearTimeout(timer);
    }

    const timer = setTimeout(
      () => dispatch(next.kind === "divider" ? { type: "reveal", total } : { type: "typing" }),
      pauseBefore(beats, visible),
    );
    return () => clearTimeout(timer);
  }, [status, visible, typing, beats, total]);

  return {
    state,
    start: useCallback(() => dispatch({ type: "start" }), []),
    pause: useCallback(() => dispatch({ type: "pause" }), []),
    resume: useCallback(() => dispatch({ type: "resume" }), []),
    skip: useCallback(() => dispatch({ type: "skip", total }), [total]),
    restart: useCallback(() => dispatch({ type: "restart" }), []),
  };
}
