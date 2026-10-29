/*
  The landing hero: the name, the one-line idea, and the way in. It has to explain the product in
  five seconds, so it says three things: who argues (the council's five orbs), what they do (the
  sentence, with the three verdicts in their colors), and where to go (the call to action).

  Adapted from the Illuminated Hero on 21st.dev (see ui/pulled/REVIEW.md). Its glow is an SVG
  filter of eight blurred, recolored layers; here the same warm layers are a CSS text-shadow,
  which is painted once and works the same in every browser. The pull's background shapes and
  load keyframes were never delivered; the Aurora takes the background's place. The orbs glide
  into a cluster, the idea kept from the User Presence Avatar pull.
*/
import { m, useReducedMotion } from "motion/react";
import { ArrowDown } from "lucide-react";
import { Aurora } from "@/components/Aurora";
import { ShimmerButton } from "@/components/ShimmerButton";
import { AgentAvatar } from "@/components/debate/AgentAvatar";
import { EASE } from "@/components/debate/shared";
import { COUNCIL } from "@/lib/agents";

/* The pull's filter layers as shadows: a near-white core, then warm orange halos that widen and
   drop. Darkmatter's primary sits in the same orange, so the glow belongs to the theme. */
const GLOW = [
  "0 0 8px rgb(255 250 246 / 0.5)",
  "0 2px 18px rgb(255 170 93 / 0.4)",
  "0 2px 38px rgb(208 126 67 / 0.65)",
  "0 2px 60px rgb(255 156 100 / 0.4)",
  "0 16px 60px rgb(116 42 0 / 0.8)",
].join(", ");

function CouncilCluster({ reduced }: { reduced: boolean }) {
  return (
    <ul aria-label="The council" className="flex items-center -space-x-2.5">
      {COUNCIL.map((agent, i) => (
        <m.li
          key={agent.name}
          title={agent.name}
          className="rounded-full ring-4 ring-background"
          initial={reduced ? false : { opacity: 0, x: -14 * (i + 1), scale: 0.8 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 360, damping: 26, delay: 0.1 + i * 0.07 }}
        >
          <AgentAvatar agent={agent} size="lg" />
          <span className="sr-only">{agent.name}</span>
        </m.li>
      ))}
    </ul>
  );
}

function Verdict({ name, children }: { name: "buy" | "wait" | "skip"; children: string }) {
  return (
    <span className="font-semibold" style={{ color: `var(--verdict-${name})` }}>
      {children}
    </span>
  );
}

export function Hero() {
  const reduced = useReducedMotion() ?? false;
  const enter = (delay: number) =>
    reduced
      ? {}
      : {
          initial: { opacity: 0, y: 14 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.7, ease: EASE, delay },
        };

  return (
    <header className="relative isolate overflow-hidden">
      <Aurora />
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-7 px-4 pb-14 pt-16 text-center sm:gap-8 sm:pb-20 sm:pt-24">
        <CouncilCluster reduced={reduced} />
        <m.h1
          {...enter(0.15)}
          className="font-mono text-[clamp(2.6rem,11vw,5rem)] font-semibold leading-[1.04] tracking-tight text-foreground-strong text-balance"
          style={{ textShadow: GLOW }}
        >
          Talk Me Out of It
        </m.h1>
        <m.p
          {...enter(0.3)}
          className="max-w-[34ch] bg-gradient-to-t from-muted-foreground to-foreground bg-clip-text text-lg leading-relaxed text-transparent text-pretty sm:text-xl"
        >
          A council of AI agents argues about the gadget you want, then rules: <Verdict name="buy">Buy</Verdict>,{" "}
          <Verdict name="wait">Wait 30 days</Verdict>, or <Verdict name="skip">Skip</Verdict>.
        </m.p>
        <m.div {...enter(0.45)}>
          <ShimmerButton href="#gallery">
            Watch the council argue
            <ArrowDown aria-hidden="true" className="size-4" strokeWidth={2.5} />
          </ShimmerButton>
        </m.div>
      </div>
    </header>
  );
}
