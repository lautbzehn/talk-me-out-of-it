import type { CSSProperties } from "react";
import type { AgentStyle } from "@/lib/agents";

/** The ease the verdict card uses too, so every entrance in the app feels the same. */
export const EASE = [0.22, 1, 0.36, 1] as const;

/**
  Sets `--agent` on an element to the member's color token. Everything inside it (the avatar glow,
  the bubble tint and border) reads var(--agent), so one member's look is one custom property.
*/
export function agentVars(agent: AgentStyle): CSSProperties {
  return { "--agent": agent.color } as CSSProperties;
}

/** A bubble: the member's color at low strength over the muted surface, with a tinted hairline. */
export const BUBBLE_SURFACE =
  "rounded-2xl rounded-tl-md border border-[color:color-mix(in_oklab,var(--agent)_28%,var(--border))] bg-[color:color-mix(in_oklab,var(--agent)_8%,var(--muted))]";
