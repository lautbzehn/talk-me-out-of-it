/*
  The one clock the chat and Under the hood's run trace share, so they always play together.

  It counts replay time (lib/playback.ts turns that into what the chat shows and where the run
  was). Either side can drive it: the chat's Pause, Skip and Replay, the trace's play button and
  its scrub rail. Everything that listens hears every change, so the two can never drift apart.

  It is a plain object rather than React state. The trace reads it every frame and writes to the
  page directly; the chat re-renders only when what it shows changes (components/debate/use-replay.ts).

  idle    waiting until the replay scrolls into view
  playing time is passing
  paused  the viewer paused, or chose a step in the trace
  done    everything is showing
*/
import { chatAt, replayAtRun, runAt, type Timeline } from "@/lib/playback";

export type ReplayStatus = "idle" | "playing" | "paused" | "done";

export class ReplayClock {
  status: ReplayStatus;
  /** Replay time, in milliseconds. */
  time: number;
  /** True when the last change was a jump (skip, seek, restart) rather than time passing. */
  jumped = true;

  private readonly listeners = new Set<() => void>();
  private raf = 0;
  private last = 0;
  private attached = false;

  constructor(
    readonly timeline: Timeline,
    reduced: boolean,
  ) {
    const finished = reduced || timeline.length === 0;
    this.status = finished ? "done" : "idle";
    this.time = finished ? timeline.length : 0;
  }

  /** Where the real run had got to, in milliseconds. */
  get run(): number {
    return runAt(this.timeline, this.time);
  }

  get chat(): { visible: number; typing: boolean } {
    return chatAt(this.timeline, this.time);
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  /** The page is showing the replay: run the frame loop if it should be running. */
  attach() {
    this.attached = true;
    if (this.status === "playing") this.loop();
  }

  detach() {
    this.attached = false;
    this.halt();
  }

  start() {
    if (this.status === "idle") this.set("playing", this.time, false);
  }

  pause() {
    if (this.status === "idle" || this.status === "playing") this.set("paused", this.time, false);
  }

  resume() {
    if (this.status === "paused") this.set("playing", this.time, false);
  }

  /** One button for play, pause and play again. */
  toggle() {
    if (this.status === "playing") this.pause();
    else if (this.status === "done") this.restart();
    else if (this.status === "idle") this.start();
    else this.resume();
  }

  skip() {
    this.set("done", this.timeline.length, true);
  }

  restart() {
    this.set("playing", 0, true);
  }

  /** Jump to a replay time. Playing stays playing; anything else is paused there. */
  seek(time: number) {
    const t = Math.min(Math.max(time, 0), this.timeline.length);
    const status = t >= this.timeline.length ? "done" : this.status === "playing" ? "playing" : "paused";
    this.set(status, t, true);
  }

  /** Jump to the moment the chat reaches a point in the real run. */
  seekRun(run: number) {
    this.seek(replayAtRun(this.timeline, run));
  }

  private set(status: ReplayStatus, time: number, jumped: boolean) {
    this.status = status;
    this.time = time;
    this.jumped = jumped;
    if (status === "playing") this.loop();
    else this.halt();
    this.emit();
  }

  private emit() {
    for (const listener of this.listeners) listener();
  }

  private loop() {
    if (this.raf || !this.attached) return;
    this.last = 0;
    this.raf = requestAnimationFrame(this.frame);
  }

  private halt() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  private readonly frame = (now: number) => {
    this.raf = 0;
    if (this.status !== "playing") return;
    // No leap after a hidden tab or a long frame: the browser stops frames while the tab is hidden.
    const dt = this.last ? Math.min(now - this.last, 100) : 0;
    this.last = now;
    this.time = Math.min(this.time + dt, this.timeline.length);
    this.jumped = false;
    if (this.time >= this.timeline.length) this.status = "done";
    else this.raf = requestAnimationFrame(this.frame);
    this.emit();
  };
}
