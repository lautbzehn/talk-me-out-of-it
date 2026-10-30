/*
  How it works: what the app is for, who is on the council, and how one purchase moves through it.
  Sits between the hero and the gallery, so a visitor learns the idea before picking a session.

  Option A of three Dan was shown (10.29.2026): a pipeline, after the AI Agent Pipeline on
  21st.dev (searched only; no code pulled). It reads as a Z. The top row runs left to right (you,
  then the intake check), drops into a bus that fans out to the four debating members, gathers
  their ratings into a second bus, and the bottom row runs left to right again (code scores it,
  the Judge explains, the verdict). On a phone it is one column with a wire between each stage.

  Motion: the stages pop in one by one as they scroll into view, and the wires draw between them.
  Once all of it is in, a small light runs along the wires in order, the way a purchase travels.
  With reduced motion everything is simply there and nothing moves.
*/
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { m, useReducedMotion, type Variants } from "motion/react";
import {
  Activity,
  ArrowUpRight,
  CodeXml,
  Laptop,
  ListChecks,
  ScanSearch,
  Sigma,
  Stamp,
  UserRound,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { AgentAvatar } from "@/components/debate/AgentAvatar";
import { EASE, agentVars } from "@/components/debate/shared";
import { VerdictPill } from "@/components/VerdictCard";
import { COUNCIL, JUDGE, type AgentStyle } from "@/lib/agents";
import { cn } from "@/lib/utils";

const REPO_URL = "https://github.com/lautbzehn/talk-me-out-of-it";

/* What each debating member does, in a visitor's words. The rubric keys are the ones each
   member's schema scores (agents/schemas.py), written out. */
const ROLES: Record<string, { role: string; rates: string; tools?: string }> = {
  "The Analyst": {
    role: "Does the math: cost per use, how long it will really last, and what you gain over what you own now.",
    rates: "value per use · longevity · upgrade gap",
    tools: "cost per use, resale value",
  },
  "Future You": {
    role: "You, six months from now. Still glad you bought it, quietly regretting it, or is it in a drawer?",
    rates: "six-month glow · want vs. reason · real use",
  },
  "Budget Guardian": {
    role: "Firmly on your side. Is this a lot of money for the problem you described, and would waiting cost you anything?",
    rates: "price for the problem · cost of waiting · better than keeping it",
  },
  "Alternatives Hunter": {
    role: "Hunts the cheaper path: refurbished, last year's model, a sale, or a newer model due soon. Flags brand lock-in too.",
    rates: "worth full price · release timing · ecosystem freedom",
    tools: "resale value",
  },
};

/* The four who debate: the council in speaking order, without the Judge. */
const DEBATERS = COUNCIL.filter((agent) => agent.name !== JUDGE.name);

/* ---- Entrance ---------------------------------------------------------------------------- */

/** Seconds between one piece and the next within a group. */
const STEP = 0.13;

/**
  The pipeline enters in five groups, top to bottom. Each number is how many steps the group
  takes, so the next group waits for it: a group starts once the page has scrolled to it and the
  one before it has finished, which keeps the order on a tall phone screen and on a desktop that
  shows it all at once.
*/
const GROUP_STEPS = [3, 8, 2, 2, 4] as const;
const GROUP = { intake: 0, council: 1, score: 2, judge: 3, verdict: 4 } as const;

/** A group counts as reached once its top is above this share of the screen's height. */
const REACH_LINE = 0.88;

function useSequence(reduced: boolean) {
  const total = GROUP_STEPS.length;
  const targets = useRef<(Element | null)[]>([]);
  const [reached, setReached] = useState(0);
  const [revealed, setRevealed] = useState(0);
  const lastRevealAt = useRef(0);

  // Count the groups the page has scrolled to. "Scrolled to" includes scrolled past: a reload
  // that lands lower down, or a jump to the gallery, must not leave the stages above it hidden.
  // (An IntersectionObserver misses that case: a group that goes from below the screen to above
  // it in one jump never intersects.)
  useEffect(() => {
    if (reduced) return;
    let frame = 0;
    const check = () => {
      frame = 0;
      const line = window.innerHeight * REACH_LINE;
      let count = 0;
      for (const el of targets.current) {
        if (!el || el.getBoundingClientRect().top >= line) break;
        count += 1;
      }
      setReached((before) => Math.max(before, count));
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(check);
    };
    check();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [reduced]);

  // Reveal the next group once it is reached and the previous group has had time to finish.
  useEffect(() => {
    if (reduced || revealed >= reached) return;
    const previous = (GROUP_STEPS[revealed - 1] ?? 0) * STEP * 1000 + 150;
    const wait = Math.max(0, lastRevealAt.current + previous - performance.now());
    const timer = window.setTimeout(() => {
      lastRevealAt.current = performance.now();
      setRevealed((count) => count + 1);
    }, wait);
    return () => window.clearTimeout(timer);
  }, [reduced, revealed, reached]);

  const shown = reduced ? total : revealed;
  return {
    /** Props for a motion element in group `group`: hidden until that group is revealed. */
    enter: (group: number) => ({ initial: reduced ? false : ("hidden" as const), animate: shown > group ? "show" : "hidden" }),
    /** Ref for the element whose arrival on screen starts group `group`. */
    target: (group: number) => (el: Element | null) => {
      targets.current[group] = el;
    },
    done: shown >= total,
  };
}

const pop: Variants = {
  hidden: { opacity: 0, y: 14, scale: 0.94 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: "spring", stiffness: 420, damping: 28, delay: i * STEP },
  }),
};

const draw: Variants = {
  hidden: { scaleX: 0, scaleY: 0, opacity: 0 },
  show: (i: number) => ({ scaleX: 1, scaleY: 1, opacity: 1, transition: { duration: 0.32, ease: EASE, delay: i * STEP } }),
};

/* ---- Wires ------------------------------------------------------------------------------- */

/**
  One connector line. `axis` is the way it runs, `reverse` flips the travel (and the draw) to
  right-to-left or bottom-to-top. `flow` is when, in seconds into the loop, the light runs along
  it; see .wire in index.css. Decorative: the stages say everything in text.
*/
function Wire({
  axis,
  reverse = false,
  flow,
  step,
  className,
  style,
}: {
  axis: "x" | "y";
  reverse?: boolean;
  flow: number;
  step: number;
  className?: string;
  style?: CSSProperties;
}) {
  const origin = axis === "x" ? (reverse ? "right" : "left") : reverse ? "bottom" : "top";
  return (
    <m.span
      aria-hidden="true"
      variants={draw}
      custom={step}
      data-axis={axis}
      data-reverse={reverse || undefined}
      className={cn("wire", axis === "x" ? "h-px" : "w-px", className)}
      style={{ transformOrigin: origin, "--flow-at": `${flow}s`, ...style } as CSSProperties}
    />
  );
}

/* Where the wires meet the cards at lg, every gap 2rem (gap-x-8). The four members sit in four
   columns of width (100% - 6rem) / 4, so the first and last centers are half that from each
   edge. The top row is two halves, so Intake's center is (100% - 2rem) / 4 from the right; the
   bottom row is three thirds, so the scoring stage's center is (100% - 4rem) / 6 from the left. */
const COL_HALF = "calc((100% - 6rem) / 8)";
const INTAKE_MID = "calc((100% - 2rem) / 4)";
const SCORE_MID = "calc((100% - 4rem) / 6)";

/**
  The band between a row and the council. At lg it is a bus: one line drops from where the flow
  comes in, runs along, and splits into the four members (fan "out"), or the four join it and it
  leaves toward the scoring stage (fan "in"). Below lg it is one wire down the middle. The label
  sits on the line either way.
*/
function Fan({ kind, label, flowStart, step }: { kind: "out" | "in"; label: string; flowStart: number; step: number }) {
  const outward = kind === "out";
  // Going out, the flow drops from Intake onto the bus and runs both ways along it to all four
  // legs. Coming in, the four legs drop onto the bus, both halves run toward the port over the
  // scoring stage, and it drops from there. The port's distance from its edge, as a CSS length:
  const port = outward ? INTAKE_MID : SCORE_MID;
  const portAt = outward ? `calc(100% - ${INTAKE_MID})` : SCORE_MID;
  const legsFlow = outward ? flowStart + 0.6 : flowStart;
  const busFlow = flowStart + 0.3;
  const portFlow = outward ? flowStart : flowStart + 0.6;

  return (
    <div aria-hidden="true" className={cn("pointer-events-none absolute inset-x-0 h-20", outward ? "-top-20" : "-bottom-20")}>
      {/* Phone and tablet: a single wire through the middle. */}
      <Wire axis="y" flow={flowStart} step={step} className="left-1/2 top-0 h-full lg:hidden" />

      {/* Desktop: the bus, split at the port so each half runs the way the purchase goes. */}
      <div className="absolute inset-0 hidden lg:block">
        <Wire
          axis="y"
          flow={portFlow}
          step={outward ? step : step + 1}
          className={outward ? "top-0 h-1/2" : "bottom-0 h-1/2"}
          style={outward ? { right: port } : { left: port }}
        />
        <Wire
          axis="x"
          reverse={outward}
          flow={busFlow}
          step={step}
          className="top-1/2"
          style={{ left: COL_HALF, width: `calc(${portAt} - ${COL_HALF})` }}
        />
        <Wire
          axis="x"
          reverse={!outward}
          flow={busFlow}
          step={step}
          className="top-1/2"
          style={{ left: portAt, right: COL_HALF }}
        />
        <div className={cn("absolute inset-x-0 grid h-1/2 grid-cols-4 gap-x-8", outward ? "bottom-0" : "top-0")}>
          {DEBATERS.map((agent) => (
            <span key={agent.name} className="relative">
              <Wire axis="y" flow={legsFlow} step={outward ? step + 1 : step} className="left-1/2 h-full" />
            </span>
          ))}
        </div>
      </div>

      <m.span
        variants={pop}
        custom={step + 1}
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-full border border-border bg-background px-3 py-1 font-mono text-[11px] text-muted-foreground"
      >
        {label}
      </m.span>
    </div>
  );
}

/* ---- Stages ------------------------------------------------------------------------------ */

function StageCard({ icon, kicker, title, children, className }: {
  icon: ReactNode;
  kicker: string;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("relative flex h-full flex-col gap-3 rounded-card border border-border bg-card p-4 sm:p-5", className)}>
      <div className="flex items-center gap-3">
        {icon}
        <div className="flex min-w-0 flex-col">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{kicker}</span>
          <h3 className="font-mono text-base font-semibold leading-snug text-foreground-strong">{title}</h3>
        </div>
      </div>
      {children}
    </div>
  );
}

function IconTile({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span
      aria-hidden="true"
      className="flex size-10 shrink-0 items-center justify-center rounded-md border border-border bg-muted/40 text-foreground"
    >
      <Icon className="size-5" strokeWidth={1.75} />
    </span>
  );
}

function AgentCard({ agent, step }: { agent: AgentStyle; step: number }) {
  const about = ROLES[agent.name];
  return (
    <m.li
      variants={pop}
      custom={step}
      style={agentVars(agent)}
      className="relative flex flex-col gap-3 rounded-card border border-[color:color-mix(in_oklab,var(--agent)_30%,var(--border))] bg-[color:color-mix(in_oklab,var(--agent)_6%,var(--card))] p-4"
    >
      <div className="flex items-center gap-2.5">
        <AgentAvatar agent={agent} size="md" />
        <h4 className="font-mono text-sm font-semibold" style={{ color: agent.color }}>
          {agent.name}
        </h4>
      </div>
      <p className="text-sm leading-relaxed text-foreground text-pretty">{about?.role}</p>
      <div className="mt-auto flex flex-col gap-1.5 border-t border-[color:color-mix(in_oklab,var(--agent)_18%,var(--border))] pt-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
        <p>
          <span className="text-foreground">Rates </span>
          {about?.rates}
        </p>
        {about?.tools ? (
          <p className="flex items-start gap-1.5">
            <Wrench aria-hidden="true" className="mt-0.5 size-3 shrink-0" />
            <span>
              <span className="text-foreground">Calls </span>
              {about.tools}
            </span>
          </p>
        ) : null}
      </div>
    </m.li>
  );
}

/* ---- The section ------------------------------------------------------------------------- */

const FACTS: { icon: LucideIcon; text: string }[] = [
  { icon: CodeXml, text: "A hand-written Python orchestrator. No agent framework." },
  { icon: Laptop, text: "Runs free on one Mac: Qwen 2.5 14B through Ollama." },
  { icon: ListChecks, text: "Every answer is checked against a schema and retried if it breaks." },
  { icon: Activity, text: "Every model call, tool call and timing is saved with the session." },
];

export function HowItWorks() {
  const reduced = useReducedMotion() ?? false;
  const { enter, target, done } = useSequence(reduced);

  return (
    <section id="how-it-works" aria-labelledby="how-title" className="mx-auto w-full max-w-5xl px-4 pb-20 pt-6 sm:px-6">
      <div className="mb-12 flex flex-col items-center gap-3 text-center">
        <p className="rounded-full border border-border bg-card/70 px-4 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          How it works
        </p>
        <h2 id="how-title" className="font-mono text-2xl font-semibold tracking-tight text-foreground-strong text-balance sm:text-3xl">
          A second opinion before you hit buy
        </h2>
        <p className="max-w-[58ch] text-base leading-relaxed text-muted-foreground text-pretty">
          You found a gadget you want. Maybe you need it, maybe it's 1 a.m. and the cart is open. Tell the council what it
          is, what it costs, why you want it and how badly. Five AI agents argue it out from different sides, and you get
          one clear call: <span className="text-buy">Buy</span>, <span className="text-wait">Wait 30 days</span>, or{" "}
          <span className="text-skip">Skip</span>, with the reason in one sentence.
        </p>
      </div>

      <ol
        aria-label="How one purchase moves through the council"
        data-flowing={done && !reduced ? "" : undefined}
        className="grid grid-cols-1 gap-x-8 gap-y-8 lg:grid-cols-12"
      >
        {/* 1. You */}
        <m.li ref={target(GROUP.intake)} {...enter(GROUP.intake)} className="relative lg:col-span-6">
          <m.div variants={pop} custom={0} className="h-full">
            <StageCard icon={<IconTile icon={UserRound} />} kicker="Step 1 · You" title="Describe the purchase">
              <ul className="flex flex-wrap gap-1.5" aria-label="What you tell it">
                {["The item", "Its price", "Why you want it", "How badly, 1 to 10", "What it replaces, if anything"].map((input) => (
                  <li key={input} className="rounded-full border border-border bg-muted/40 px-2.5 py-1 font-mono text-[11px] text-foreground">
                    {input}
                  </li>
                ))}
              </ul>
            </StageCard>
          </m.div>
          <Wire axis="x" flow={0} step={1} className="left-full top-1/2 hidden w-8 lg:block" />
          <Wire axis="y" flow={0} step={1} className="left-1/2 top-full hidden h-8 max-lg:block" />
        </m.li>

        {/* 2. Intake */}
        <m.li {...enter(GROUP.intake)} className="relative lg:col-span-6">
          <m.div variants={pop} custom={2} className="h-full">
            <StageCard icon={<IconTile icon={ScanSearch} />} kicker="Step 2 · Intake" title="A quick check">
              <p className="text-sm leading-relaxed text-muted-foreground text-pretty">
                Is it a gadget? Anything in your answer that tries to give the council orders is set aside.
              </p>
            </StageCard>
          </m.div>
        </m.li>

        {/* 3. The council */}
        <m.li ref={target(GROUP.council)} {...enter(GROUP.council)} className="relative mt-12 mb-12 lg:col-span-12">
          <h3 className="sr-only">Step 3 · The council debates: two rounds, and a third only if they are split</h3>
          <Fan kind="out" label="Step 3 · The debate: 2 or 3 rounds" flowStart={0.45} step={0} />
          <ul className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
            {DEBATERS.map((agent, i) => (
              <AgentCard key={agent.name} agent={agent} step={i + 2} />
            ))}
          </ul>
          <Fan kind="in" label="12 ratings, 1 to 10 each" flowStart={2.1} step={6} />
        </m.li>

        {/* 4. Code scores it */}
        <m.li ref={target(GROUP.score)} {...enter(GROUP.score)} className="relative lg:col-span-4">
          <m.div variants={pop} custom={0} className="h-full">
            <StageCard icon={<IconTile icon={Sigma} />} kicker="Step 4 · Code, not AI" title="Python scores it">
              <p className="text-sm leading-relaxed text-muted-foreground text-pretty">
                It averages the agents' final ratings. The model never writes the number.
              </p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-md border border-border bg-background/60 px-3 py-2.5 font-mono text-xs tabular-nums">
                <dt className="text-muted-foreground">5.5 and up</dt>
                <dd className="text-buy">Buy</dd>
                <dt className="text-muted-foreground">4.5 to 5.5</dt>
                <dd className="text-wait">Wait 30 days</dd>
                <dt className="text-muted-foreground">under 4.5</dt>
                <dd className="text-skip">Skip</dd>
              </dl>
              <p className="font-mono text-[11px] leading-relaxed text-muted-foreground">
                A Buy needs one agent leaning Buy, a Skip one leaning Skip. Otherwise it waits.
              </p>
            </StageCard>
          </m.div>
          <Wire axis="x" flow={2.95} step={1} className="left-full top-1/2 hidden w-8 lg:block" />
          <Wire axis="y" flow={2.95} step={1} className="left-1/2 top-full hidden h-8 max-lg:block" />
        </m.li>

        {/* 5. The Judge */}
        <m.li ref={target(GROUP.judge)} {...enter(GROUP.judge)} className="relative lg:col-span-4">
          <m.div variants={pop} custom={0} className="h-full">
            <StageCard
              icon={<AgentAvatar agent={JUDGE} size="lg" />}
              kicker="Step 5 · The Judge"
              title="Explains the ruling"
            >
              <p className="text-sm leading-relaxed text-muted-foreground text-pretty">
                Reads the whole debate and sums up the verdict in one sentence. Its answer has no slot for a verdict or a
                score, so it can't pick one.
              </p>
            </StageCard>
          </m.div>
          <Wire axis="x" flow={3.35} step={1} className="left-full top-1/2 hidden w-8 lg:block" />
          <Wire axis="y" flow={3.35} step={1} className="left-1/2 top-full hidden h-8 max-lg:block" />
        </m.li>

        {/* 6. The verdict */}
        <m.li ref={target(GROUP.verdict)} {...enter(GROUP.verdict)} className="relative lg:col-span-4">
          <m.div variants={pop} custom={0} className="h-full">
            <StageCard icon={<IconTile icon={Stamp} />} kicker="Step 6 · You again" title="Your verdict">
              <ul className="flex flex-col items-start gap-2" aria-label="The three possible verdicts">
                {(
                  [
                    ["buy", "Buy"],
                    ["wait", "Wait 30 days"],
                    ["skip", "Skip"],
                  ] as const
                ).map(([verdict, label], i) => (
                  <m.li key={verdict} variants={pop} custom={i + 1}>
                    <VerdictPill verdict={verdict} label={label} />
                  </m.li>
                ))}
              </ul>
              <p className="text-sm leading-relaxed text-muted-foreground">With the reason in one sentence.</p>
            </StageCard>
          </m.div>
        </m.li>
      </ol>

      {/* For the technical visitor: what is under the hood, and where to read it. */}
      <div className="mt-14 flex flex-col gap-6 rounded-card border border-border bg-card/60 p-5 sm:p-6">
        <div className="flex flex-col gap-1.5">
          <h3 className="font-mono text-base font-semibold text-foreground-strong">The model judges. The code calculates.</h3>
          <p className="text-sm leading-relaxed text-muted-foreground text-pretty">
            Built from scratch to show how a multi-agent system works inside. Open any session's Under the hood to see its
            prompts, tool calls and the scoring math.
          </p>
        </div>
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {FACTS.map(({ icon: Icon, text }) => (
            <li key={text} className="flex items-start gap-3 text-sm leading-relaxed text-foreground">
              <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" strokeWidth={1.75} />
              {text}
            </li>
          ))}
        </ul>
        <a
          href={REPO_URL}
          className="-my-1.5 inline-flex items-center gap-1.5 self-start py-1.5 font-mono text-xs text-foreground underline decoration-border underline-offset-4 transition-colors hover:text-foreground-strong hover:decoration-primary"
        >
          Read the code on GitHub
          <ArrowUpRight aria-hidden="true" className="size-3.5" />
        </a>
      </div>
    </section>
  );
}
