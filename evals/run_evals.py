"""The eval runner: the whole council on every scenario, then a report.

Run from the project folder with:
  .venv/bin/python -m evals.run_evals                     every scenario once (about 50 minutes)
  .venv/bin/python -m evals.run_evals --only road-bike,commute-headphones
  .venv/bin/python -m evals.run_evals --repeats 3         each scenario 3 times, to see how stable it is
  .venv/bin/python -m evals.run_evals --model qwen2.5:7b    another downloaded local model (the faster fallback)
  .venv/bin/python -m evals.run_evals --rebuild evals/runs/<run id>    the report again, no model calls

"-m" runs this file as a module of the project, so its imports (agents, council, scoring)
are found the same way the tests find them.

Each run gets its own folder, evals/runs/<run id>/:
  run.json      what was run: the model, the scoring formula version, the scenarios themselves
  sessions/     one session per council, exactly what run_council returned (git ignores these)
  report.md     the report people read, also printed at the end
  report.json   the same numbers as data, for comparing runs later

The report is rewritten after every council, so stopping a long run with Ctrl+C still leaves
a report of everything that finished.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ollama

import config
import scoring
from agents.base import client, default_chat
from council import CouncilError, run_council
from evals.report import LABELS, minutes, render, row_for, summarize
from evals.scenarios import Scenario, ScenarioSet, load_scenarios

RUNS = Path(__file__).parent / "runs"
SECONDS_PER_COUNCIL = 400  # rough, from the 14B pass (5.5 to 8.7 minutes); only for the estimate shown at the start


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id() -> str:
    """Example: 20261025-231500-qwen2.5-14b-v1. Sorts by time, and says which model and formula ran."""
    model = "".join(ch if ch.isalnum() or ch == "." else "-" for ch in config.MODEL)
    return f"{datetime.now():%Y%m%d-%H%M%S}-{model}-v{scoring.FORMULA_VERSION}"


def session_file(folder: Path, scenario_id: str, repeat: int) -> Path:
    return folder / "sessions" / f"{scenario_id}-r{repeat}.json"


def error_session(scenario: Scenario, message: str, seconds: float) -> dict:
    """What gets saved when the council stops (for example, fewer than two members answered),
    so the run goes on and the report counts it instead of crashing."""
    return {
        "kind": "error",
        "error": message,
        "created_at": now(),
        "model": config.MODEL,
        "purchase": scenario.purchase.model_dump(),
        "rounds": [],
        "timing": {"total_seconds": round(seconds, 2)},
    }


def progress(say):
    """A short live line for each step, so a 50 minute run shows it is still moving."""
    def on_event(event):
        kind = event["event"]
        if kind == "intake_done":
            found = f"a gadget ({event['category']})" if event["is_tech_gadget"] else "not a gadget"
            say(f"    intake: {found}")
        elif kind == "agent_done":
            say(f"    round {event['round']}: {event['agent']} {event['status']} ({minutes(event['seconds'])})")
        elif kind == "scored":
            say(f"    scored {event['score']}: {event['verdict_label']}")
    return on_event


def write_report(folder: Path, info: dict, rows: list[dict]) -> str:
    summary = summarize(rows)
    text = render(info, rows, summary)
    (folder / "report.md").write_text(text)
    run = {key: value for key, value in info.items() if key != "scenarios"}
    (folder / "report.json").write_text(json.dumps({"run": run, "summary": summary, "rows": rows}, indent=2))
    return text


def run_evals(scenarios: list[Scenario], folder: Path, scenarios_version: str, repeats: int = 1,
              chat=default_chat, say=print, timeout_seconds: int = config.REQUEST_TIMEOUT_SECONDS) -> str:
    """Run the council on every scenario `repeats` times, saving as it goes. Returns the report."""
    (folder / "sessions").mkdir(parents=True, exist_ok=True)
    info = {
        "run_id": folder.name,
        "model": config.MODEL,
        "formula_version": scoring.FORMULA_VERSION,
        "scenarios_version": scenarios_version,
        "repeats": repeats,
        "request_timeout_seconds": timeout_seconds,
        "started_at": now(),
        "finished_at": None,
        "scenarios": [scenario.model_dump() for scenario in scenarios],
    }
    (folder / "run.json").write_text(json.dumps(info, indent=2))

    rows, total, done = [], len(scenarios) * repeats, 0
    for repeat in range(1, repeats + 1):
        for scenario in scenarios:
            done += 1
            say(f"\n[{done}/{total}] {scenario.id}: {scenario.purchase.item} (expected {LABELS[scenario.expected]})")
            started = time.perf_counter()
            try:
                session = run_council(scenario.purchase, chat=chat, on_event=progress(say))
            except CouncilError as error:
                session = error_session(scenario, str(error), time.perf_counter() - started)
            session_file(folder, scenario.id, repeat).write_text(json.dumps(session, indent=2))

            row = row_for(scenario, session, repeat)
            rows.append(row)
            verdict = "right" if row["match"] else f"expected {LABELS[row['expected']]}"
            say(f"    -> {LABELS[row['got']]}, {verdict} ({minutes(row['seconds'])})")
            write_report(folder, info, rows)

    info["finished_at"] = now()
    (folder / "run.json").write_text(json.dumps(info, indent=2))
    return write_report(folder, info, rows)


def rebuild(folder: Path) -> str:
    """Make the report again from a run's saved sessions. No model is called."""
    info = json.loads((folder / "run.json").read_text())
    scenarios = [Scenario.model_validate(data) for data in info["scenarios"]]
    rows = []
    for repeat in range(1, info["repeats"] + 1):
        for scenario in scenarios:
            path = session_file(folder, scenario.id, repeat)
            if path.exists():  # a run stopped early has fewer sessions
                rows.append(row_for(scenario, json.loads(path.read_text()), repeat))
    return write_report(folder, info, rows)


def use_model(name: str, available: list[str]) -> None:
    """Point the whole engine at another local model for this run. Every model call reads
    config.MODEL when it runs, so setting it once here is enough."""
    if name not in available:
        raise SystemExit(f"{name} is not downloaded. Get it with:  ollama pull {name}")
    config.MODEL = name


def pick(scenario_set: ScenarioSet, only: str | None) -> list[Scenario]:
    if not only:
        return scenario_set.scenarios
    wanted = [name.strip() for name in only.split(",") if name.strip()]
    known = {scenario.id for scenario in scenario_set.scenarios}
    unknown = [name for name in wanted if name not in known]
    if unknown:
        raise SystemExit(f"Unknown scenario id(s): {', '.join(unknown)}. Known: {', '.join(sorted(known))}")
    return [scenario for scenario in scenario_set.scenarios if scenario.id in wanted]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the council on the eval scenarios and report how often it agrees.")
    parser.add_argument("--only", help="comma-separated scenario ids to run, instead of all of them")
    parser.add_argument("--repeats", type=int, default=1, choices=range(1, 6), metavar="1-5",
                        help="run each scenario this many times (the model varies between runs)")
    parser.add_argument("--rebuild", type=Path, metavar="RUN_FOLDER", help="rebuild a run's report without the model")
    parser.add_argument("--model", help=f"another local Ollama model for this run (default {config.MODEL})")
    parser.add_argument("--timeout", type=int, metavar="SECONDS",
                        help=f"how long one model call may take (default {config.REQUEST_TIMEOUT_SECONDS}); a slower model needs more")
    args = parser.parse_args(argv)

    if args.rebuild:
        print(rebuild(args.rebuild))
        return
    if args.model:
        use_model(args.model, [model.model for model in client.list().models])

    scenario_set = load_scenarios()
    scenarios = pick(scenario_set, args.only)
    folder = RUNS / new_run_id()
    councils = sum(scenario.expected != "declined" for scenario in scenarios) * args.repeats
    print(f"Eval run {folder.name}: {len(scenarios) * args.repeats} scenario run(s),"
          f" roughly {minutes(councils * SECONDS_PER_COUNCIL)}. Ctrl+C stops it and keeps the report so far.")
    try:
        # The shared client's timeout is fixed when it is created, so a different timeout needs its own client.
        chat = ollama.Client(timeout=args.timeout).chat if args.timeout else default_chat
        report = run_evals(scenarios, folder, scenario_set.version, repeats=args.repeats, chat=chat,
                           timeout_seconds=args.timeout or config.REQUEST_TIMEOUT_SECONDS)
    except KeyboardInterrupt:
        print(f"\nStopped. The report covers every council that finished: {folder / 'report.md'}")
        sys.exit(1)
    except ConnectionError:
        print("Can't reach Ollama. Start it with:  brew services start ollama")
        sys.exit(1)
    print("\n" + report)
    print(f"Saved to {folder}")


if __name__ == "__main__":
    main()
