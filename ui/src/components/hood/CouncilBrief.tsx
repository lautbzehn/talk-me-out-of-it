/*
  Who was in the room and what each was told: the role, voice, rubric, tools and the full system
  prompt each member ran with, as the session saved them in its engine block. Native <details>
  elements, so each brief opens with the keyboard and works without JavaScript.
*/
import { AgentAvatar } from "@/components/debate/AgentAvatar";
import { agentStyle, JUDGE } from "@/lib/agents";
import type { Hood } from "@/lib/hood";
import { humanize } from "@/lib/run-trace";

function Prompt({ text }: { text: string }) {
  return (
    <pre className="max-h-72 overflow-auto rounded-md border border-border bg-background/60 p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words text-foreground">
      {text}
    </pre>
  );
}

function Summary({ name, line }: { name: string; line: string }) {
  const agent = agentStyle(name);
  return (
    <summary className="flex cursor-pointer list-none items-start gap-2.5 py-2 [&::-webkit-details-marker]:hidden">
      <AgentAvatar agent={agent} size="sm" className="mt-0.5" />
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="font-mono text-xs font-semibold" style={{ color: agent.color }}>
          {name}
        </span>
        <span className="text-sm text-muted-foreground text-pretty">{line}</span>
      </span>
    </summary>
  );
}

export function CouncilBrief({ hood }: { hood: Hood }) {
  if (hood.members.length === 0) return <p className="text-sm text-muted-foreground">This session did not save the council's brief.</p>;
  return (
    <ul className="flex flex-col divide-y divide-border">
      {hood.members.map((member) => (
        <li key={member.name}>
          <details>
            <Summary name={member.name} line={`Focus: ${member.focus}`} />
            <div className="flex flex-col gap-3 pb-4 pl-8.5 text-sm leading-relaxed text-foreground">
              <p>
                <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">Voice </span>
                {member.voice}
              </p>
              <div>
                <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">Rubric</p>
                <dl className="mt-1 flex flex-col gap-1">
                  {Object.entries(member.rubric).map(([key, text]) => (
                    <div key={key}>
                      <dt className="inline font-mono text-xs text-foreground-strong">{humanize(key)}: </dt>
                      <dd className="inline">{text}</dd>
                    </div>
                  ))}
                </dl>
              </div>
              <p>
                <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">Tools </span>
                {member.tools.length === 0
                  ? "none"
                  : member.tools.map((tool) => (member.requiredTools.includes(tool) ? `${tool} (required)` : tool)).join(", ")}
              </p>
              <Prompt text={member.systemPrompt} />
            </div>
          </details>
        </li>
      ))}
      {hood.judgePrompt ? (
        <li>
          <details>
            <Summary name={JUDGE.name} line="Explains the verdict code worked out. It has no verdict or score to fill in." />
            <div className="pb-4 pl-8.5">
              <Prompt text={hood.judgePrompt} />
            </div>
          </details>
        </li>
      ) : null}
    </ul>
  );
}
