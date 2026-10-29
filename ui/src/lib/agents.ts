/*
  Who is in the room: each council member's icon and color token. The names are the ones the
  engine writes into every transcript (agents/*.py), so a lookup by name always finds the member.
  The colors live in index.css as --agent-*; nothing here names a hex value.
*/
import { Calculator, CircleHelp, Gavel, Hourglass, Search, ShieldCheck, type LucideIcon } from "lucide-react";

export interface AgentStyle {
  name: string;
  icon: LucideIcon;
  /** A CSS value that resolves to the member's color, e.g. var(--agent-analyst). */
  color: string;
}

const MEMBERS: readonly AgentStyle[] = [
  { name: "The Analyst", icon: Calculator, color: "var(--agent-analyst)" },
  { name: "Future You", icon: Hourglass, color: "var(--agent-future)" },
  { name: "Budget Guardian", icon: ShieldCheck, color: "var(--agent-guardian)" },
  { name: "Alternatives Hunter", icon: Search, color: "var(--agent-hunter)" },
];

export const JUDGE: AgentStyle = { name: "The Judge", icon: Gavel, color: "var(--agent-judge)" };

/** Everyone in speaking order, the Judge last. The hero shows them as a cluster of orbs. */
export const COUNCIL: readonly AgentStyle[] = [...MEMBERS, JUDGE];

const BY_NAME = new Map<string, AgentStyle>(COUNCIL.map((agent) => [agent.name, agent]));

/** A name the UI has never seen (a future council member) still gets a quiet, neutral style. */
export function agentStyle(name: string): AgentStyle {
  return BY_NAME.get(name) ?? { name, icon: CircleHelp, color: "var(--muted-foreground)" };
}
