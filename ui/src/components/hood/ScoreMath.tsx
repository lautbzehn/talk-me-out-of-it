/*
  How the verdict was worked out, in four steps a stranger can check by hand: the ratings that
  count, their average, the cut-offs, and the lean rule. This is the project's central claim made
  visible: the model judges (it writes ratings and leans), the code calculates (everything else).

  The arithmetic shown here is redone in the browser from the saved ratings, then compared with
  the score the engine saved. They agree on every gallery session; if a file ever disagreed, the
  page would say so rather than hide it.
*/
import type { ReactNode } from "react";
import { AgentAvatar } from "@/components/debate/AgentAvatar";
import { VerdictPill } from "@/components/VerdictCard";
import { agentStyle } from "@/lib/agents";
import type { Hood, HoodTurn, Rules, Scoring } from "@/lib/hood";
import { humanize } from "@/lib/run-trace";
import type { Lean } from "@/lib/transcript";
import { cn } from "@/lib/utils";

const LEAN_LABEL: Record<Lean, string> = { buy: "Buy", wait: "Wait", skip: "Skip" };
const VERDICT_LABEL: Record<Lean, string> = { buy: "Buy", wait: "Wait 30 days", skip: "Skip" };

function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <li className="relative flex gap-3">
      <span
        aria-hidden="true"
        className="flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-muted font-mono text-[11px] text-foreground tabular-nums"
      >
        {n}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-2.5 pt-0.5">
        <p className="font-mono text-xs font-semibold text-foreground-strong">{title}</p>
        {children}
      </div>
    </li>
  );
}

/** The last turn each member gave a valid answer in: those ratings are the ones scored. */
function finalTurns(hood: Hood): Map<string, { turn: HoodTurn; round: number }> {
  const out = new Map<string, { turn: HoodTurn; round: number }>();
  for (const round of hood.rounds) {
    for (const turn of round.turns) if (turn.status === "ok") out.set(turn.agent, { turn, round: round.number });
  }
  return out;
}

function Ratings({ hood, scoring, rules }: { hood: Hood; scoring: Scoring; rules: Rules }) {
  const finals = finalTurns(hood);
  const sat = [...new Set(hood.rounds.flatMap((r) => r.turns.map((t) => t.agent)))].filter((name) => !(name in scoring.inputs));
  return (
    <div className="flex flex-col gap-3">
      {Object.entries(scoring.inputs).map(([name, ratings]) => {
        const agent = agentStyle(name);
        const final = finals.get(name);
        const rubric = hood.members.find((m) => m.name === name)?.rubric ?? {};
        return (
          <div key={name} className="flex flex-col gap-1.5">
            <p className="flex items-center gap-2 font-mono text-xs">
              <AgentAvatar agent={agent} size="xs" />
              <span style={{ color: agent.color }} className="font-semibold">
                {name}
              </span>
              {final ? <span className="text-muted-foreground">round {final.round}</span> : null}
            </p>
            <ul className="flex flex-wrap gap-1.5 pl-7">
              {Object.entries(ratings).map(([key, score]) => {
                const counted = (rules.weights[key] ?? 1) !== 0 && !scoring.notCounted.includes(key);
                return (
                  <li
                    key={key}
                    title={rubric[key]}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-[11px]",
                      counted ? "border-border bg-muted/40 text-foreground" : "border-dashed border-border text-muted-foreground",
                    )}
                  >
                    {humanize(key)}
                    <span className={cn("font-semibold tabular-nums", counted ? "text-foreground-strong" : "line-through")}>{score}</span>
                    {counted ? null : <span>not counted</span>}
                  </li>
                );
              })}
            </ul>
            {final && Object.keys(final.turn.ratings).length > 0 ? (
              <details className="group pl-7">
                <summary className="-my-1 w-fit cursor-pointer py-1 font-mono text-[11px] text-muted-foreground hover:text-foreground">
                  The reasons it gave
                </summary>
                <dl className="mt-2 flex flex-col gap-1.5 text-sm leading-relaxed">
                  {Object.entries(final.turn.ratings).map(([key, rating]) => (
                    <div key={key}>
                      <dt className="inline font-mono text-xs text-muted-foreground">
                        {humanize(key)} {rating.score}:{" "}
                      </dt>
                      <dd className="inline text-foreground">{rating.reason}</dd>
                    </div>
                  ))}
                </dl>
              </details>
            ) : null}
          </div>
        );
      })}
      {sat.map((name) => (
        <p key={name} className="text-sm text-muted-foreground">
          {name} sat out, so it has no ratings to count.
        </p>
      ))}
    </div>
  );
}

function Average({ scoring, rules }: { scoring: Scoring; rules: Rules }) {
  const counted = Object.values(scoring.inputs).flatMap((ratings) =>
    Object.entries(ratings)
      .filter(([key]) => (rules.weights[key] ?? 1) !== 0 && !scoring.notCounted.includes(key))
      .map(([key, score]) => ({ score, weight: rules.weights[key] ?? 1 })),
  );
  const plain = counted.every((c) => c.weight === 1);
  const sum = counted.reduce((s, c) => s + c.score * c.weight, 0);
  const weights = counted.reduce((s, c) => s + c.weight, 0);
  const average = weights > 0 ? sum / weights : 0;
  const agrees = Math.abs(Math.round(average * 10) / 10 - scoring.score) < 0.051 && counted.length === scoring.ratingsCounted;

  return (
    <div className="flex flex-col gap-1.5 font-mono text-[13px] leading-relaxed text-foreground tabular-nums">
      <p className="break-words">
        {plain ? counted.map((c) => c.score).join(" + ") : counted.map((c) => `${c.weight}×${c.score}`).join(" + ")} ={" "}
        <span className="text-foreground-strong">{sum}</span>
      </p>
      <p>
        {sum} ÷ {weights} ratings = {average.toFixed(2)}, shown as{" "}
        <span className="font-semibold text-foreground-strong">{scoring.score.toFixed(1)}</span>
      </p>
      {agrees ? null : (
        <p className="font-sans text-sm text-muted-foreground">
          This page's arithmetic does not match the saved score of {scoring.score.toFixed(1)}; the saved one is shown.
        </p>
      )}
    </div>
  );
}

function CutOffs({ scoring, rules }: { scoring: Scoring; rules: Rules }) {
  const { score, scoreVerdict } = scoring;
  const where =
    scoreVerdict === "buy"
      ? `${score.toFixed(1)} is ${rules.buyAt} or more`
      : scoreVerdict === "skip"
        ? `${score.toFixed(1)} is below ${rules.waitAt}`
        : `${score.toFixed(1)} is between ${rules.waitAt} and ${rules.buyAt}`;
  return (
    <div className="flex flex-col gap-1.5 text-sm leading-relaxed text-foreground">
      <p>
        {rules.buyAt} and above is Buy, below {rules.waitAt} is Skip, anything between is Wait 30 days.
      </p>
      <p>
        {where}, so the score alone says <span className="font-semibold text-foreground-strong">{VERDICT_LABEL[scoreVerdict]}</span>.
      </p>
    </div>
  );
}

function LeanRule({ scoring }: { scoring: Scoring }) {
  const { scoreVerdict, verdict, leans, railNote } = scoring;
  const needed = scoreVerdict === "wait" ? null : scoreVerdict;
  const backers = needed ? Object.entries(leans).filter(([, l]) => l === needed).map(([name]) => name) : [];
  const outcome =
    needed === null
      ? "A Wait needs no lean, so the verdict stays Wait 30 days."
      : verdict !== scoreVerdict
        ? (railNote ?? `No member leaned ${LEAN_LABEL[needed]}, so the verdict holds at Wait 30 days.`)
        : `${joinNames(backers)} ${backers.length === 1 ? "leans" : "lean"} ${LEAN_LABEL[needed]}, so the verdict stays ${VERDICT_LABEL[needed]}.`;

  return (
    <div className="flex flex-col gap-2.5 text-sm leading-relaxed text-foreground">
      <p>Buy needs at least one member leaning Buy, and Skip needs at least one leaning Skip. Otherwise the verdict is Wait 30 days.</p>
      <ul className="flex flex-wrap gap-1.5" aria-label="Final leans">
        {Object.entries(leans).map(([name, l]) => {
          const color = `var(--verdict-${l})`;
          return (
            <li key={name} className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 font-mono text-[11px]">
              <span aria-hidden="true" className="size-1.5 rounded-full" style={{ background: color }} />
              <span className="text-muted-foreground">{name}</span>
              <span className="font-semibold" style={{ color }}>
                {LEAN_LABEL[l]}
              </span>
            </li>
          );
        })}
      </ul>
      <p className={cn(verdict !== scoreVerdict && "rounded-card border border-border bg-muted/40 px-3 py-2")}>{outcome}</p>
    </div>
  );
}

export function ScoreMath({ hood }: { hood: Hood }) {
  const { scoring, rules } = hood;
  if (!scoring || !rules) {
    return <p className="text-sm text-muted-foreground">This session has no scoring record.</p>;
  }
  return (
    <ol className="flex flex-col gap-6">
      <Step n={1} title="The ratings that count">
        <p className="text-sm text-muted-foreground">
          Each member's last valid turn. 10 favors buying, 1 argues against. The council's brief, further down, says what each
          rating measures.
        </p>
        <Ratings hood={hood} scoring={scoring} rules={rules} />
      </Step>
      <Step n={2} title="Their average">
        <Average scoring={scoring} rules={rules} />
      </Step>
      <Step n={3} title="The cut-offs">
        <CutOffs scoring={scoring} rules={rules} />
      </Step>
      <Step n={4} title="The lean rule">
        <LeanRule scoring={scoring} />
      </Step>
      <li className="flex flex-wrap items-center gap-3 rounded-card border border-border bg-muted/30 px-4 py-3">
        <VerdictPill verdict={scoring.verdict} label={scoring.verdictLabel} />
        <p className="flex-1 text-sm leading-relaxed text-foreground">
          Code worked out every number here from the ratings. The model wrote only the ratings and the leans.
        </p>
      </li>
    </ol>
  );
}
