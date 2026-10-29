/*
  The run in numbers: every count here is worked out from the trace, and the settings come from
  the engine block the session saved about itself.
*/
import type { Attempt, Hood } from "@/lib/hood";
import { formatDuration } from "@/lib/gallery";
import { groupDigits } from "@/lib/run-trace";

function tally(hood: Hood) {
  const attempts: Attempt[] = [
    ...hood.intake.attempts,
    ...hood.rounds.flatMap((r) => r.turns.flatMap((t) => t.attempts)),
    ...(hood.judge?.attempts ?? []),
  ];
  const toolSteps = hood.rounds.flatMap((r) => r.turns.flatMap((t) => t.modelCalls));
  const tools = hood.rounds.flatMap((r) => r.turns.flatMap((t) => t.toolCalls));
  const calls = [...attempts, ...toolSteps];
  return {
    modelCalls: calls.length,
    toolCalls: tools.length,
    toolsRejected: tools.filter((t) => !t.ok).length,
    sentBack: attempts.filter((a) => !a.ok).length,
    read: calls.reduce((s, c) => s + c.promptTokens, 0),
    written: calls.reduce((s, c) => s + c.outputTokens, 0),
  };
}

export function RunFacts({ hood }: { hood: Hood }) {
  const t = tally(hood);
  const rules = hood.rules;
  const tiebreak = hood.rounds.some((r) => r.kind === "tiebreak");
  const facts: [string, string][] = [
    ["Model", `${hood.model}, running locally`],
    ["Run time", formatDuration(hood.totalSeconds)],
    ["Rounds", hood.rounds.length === 0 ? "none (declined at intake)" : `${hood.rounds.length}${tiebreak ? ", with a tiebreak" : ""}`],
    ["Model calls", String(t.modelCalls)],
    ["Tool calls", t.toolsRejected > 0 ? `${t.toolCalls}, ${t.toolsRejected} rejected` : String(t.toolCalls)],
    ["Answers sent back", String(t.sentBack)],
    ["Tokens read", groupDigits(t.read)],
    ["Tokens written", groupDigits(t.written)],
    [
      "Injection guard",
      hood.guard.triggered
        ? `set aside ${hood.guard.removed.length} sentence${hood.guard.removed.length === 1 ? "" : "s"} (caught by ${hood.guard.by.map((b) => (b === "patterns" ? "code patterns" : "the intake check")).join(" and ")})`
        : "nothing to set aside",
    ],
  ];
  if (rules) {
    const settings = [
      rules.temperature !== null ? `temperature ${rules.temperature}` : null,
      rules.contextTokens !== null ? `${groupDigits(rules.contextTokens)}-token context` : null,
      rules.maxAttempts !== null ? `${rules.maxAttempts} tries per answer` : null,
      rules.maxRounds !== null ? `up to ${rules.maxRounds} rounds` : null,
    ].filter(Boolean);
    facts.push(["Settings", settings.join(" · ")]);
  }

  return (
    <div className="flex flex-col gap-3">
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2.5 sm:grid-cols-2">
        {facts.map(([label, value]) => (
          <div key={label} className="flex flex-col gap-0.5">
            <dt className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">{label}</dt>
            <dd className="font-mono text-[13px] text-foreground tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      {hood.guard.triggered && hood.guard.removed.length > 0 ? (
        <div className="rounded-card border border-border bg-muted/30 px-3 py-2 text-sm leading-relaxed">
          <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">What the guard set aside</p>
          <ul className="mt-1 flex flex-col gap-0.5 text-foreground">
            {hood.guard.removed.map((sentence) => (
              <li key={sentence}>“{sentence}”</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
