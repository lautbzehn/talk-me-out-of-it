"""The replay tool: rebuild a saved session and rerun one part of it, without the council.

A full council takes about four minutes of model time. Scoring needs no model at all, and the
Judge needs one call. So when scoring.py or the Judge's prompt changes, there is no need to
run the debate again: rebuild it from the saved session and rerun only that part. The same
debate, scored or judged two ways, is also a fairer comparison than two separate runs,
because the model never gives the same debate twice.

Run from the project folder with:
  .venv/bin/python -m evals.replay evals/runs/<run id>            rescore every session with today's scoring.py
  .venv/bin/python -m evals.replay evals/runs/<run id> --judge    rerun the Judge too (one model call per council)
  .venv/bin/python -m evals.replay evals/runs/<run id> --save     also save the replay next to the run

Saved sessions are never changed. Step 4 calls `replay_run(folder, score=candidate)` from
Python to try candidate formulas on the same debates.
"""

import argparse
import json
from pathlib import Path

import scoring
from agents import judge
from agents.base import default_chat
from agents.guard import purchase_as_read
from agents.roster import COUNCIL
from agents.schemas import Purchase
from debate import Debate, Round, Turn, final_replies
from evals.report import LABELS, render, row_for, share, summarize
from evals.run_evals import session_file
from evals.scenarios import Scenario

AGENTS = {agent.name: agent for agent in COUNCIL}

# Rubric keys renamed since some sessions were saved: old name -> new name. The scores stay as
# the model gave them; only the key moves, so an old session still fits today's schema.
RENAMED_KEYS = {}


def current_keys(reply: dict) -> dict:
    ratings = {RENAMED_KEYS.get(name, name): rating for name, rating in reply["ratings"].items()}
    return {**reply, "ratings": ratings}


def rebuild_debate(session: dict) -> Debate:
    """The saved session turned back into the Debate the orchestrator had: validated replies,
    rounds, and traces (the digest's tool results come from the traces)."""
    if session.get("kind") != "council":
        raise ValueError(f"a {session.get('kind')} session has no debate to replay")
    rounds = []
    for saved in session["rounds"]:
        turns = []
        for turn in saved["turns"]:
            reply = None
            if turn["status"] == "ok":
                agent = AGENTS[turn["agent"]]
                schema = agent.take_schema if saved["kind"] == "opening" else agent.rebuttal_schema
                # "saved": this reply passed the rules of its day; text rules added later don't judge it again.
                reply = schema.model_validate(current_keys(turn["take_or_rebuttal"]), context={"saved": True})
            turns.append(Turn(turn["agent"], turn["status"], reply, turn["trace"], turn["seconds"], turn["changes"]))
        rounds.append(Round(saved["number"], saved["kind"], turns, saved["seconds"]))
    category = (session.get("intake") or {}).get("category")
    # The agents read the purchase with anything the injection guard set aside removed.
    purchase = purchase_as_read(Purchase.model_validate(session["purchase"]), session.get("guard"))
    return Debate(purchase, rounds, category)


def rescore(session: dict, score=scoring.score, rounds: int | None = None) -> dict:
    """Score the saved debate again. `score` is any function shaped like scoring.score.
    With `rounds=1`, only the opening round counts: the verdict before any rebuttal."""
    debate = rebuild_debate(session)
    if rounds is not None:
        debate.rounds = debate.rounds[:rounds]
    return score(final_replies(debate))


def rejudge(session: dict, result: dict, chat=default_chat) -> dict:
    """Run today's Judge on the saved debate and a scoring result. One model call (more on retries)."""
    ruling, trace, fallback_used = judge.rule(rebuild_debate(session), result, chat=chat)
    return {**ruling.model_dump(), "fallback_used": fallback_used, "trace": trace}


def replayed(session: dict, score=scoring.score, with_judge: bool = False, chat=default_chat) -> dict:
    """A copy of the session with scoring (and the Judge, if asked) done again. Declines and
    errors come back unchanged: there is nothing to rescore."""
    if session.get("kind") != "council":
        return session
    result = rescore(session, score)
    copy = {**session, "scoring": result}
    if with_judge:
        copy["judge"] = rejudge(session, result, chat=chat)
    return copy


def replay_run(folder: Path, score=scoring.score, with_judge: bool = False, chat=default_chat) -> dict:
    """Replay every saved session of an eval run. Returns the run info, the formula version
    used, the stored rows, the replayed rows, and each council's verdict after the opening
    round alone (keyed by "<scenario id>-r<repeat>")."""
    info = json.loads((folder / "run.json").read_text())
    scenarios = [Scenario.model_validate(data) for data in info["scenarios"]]
    stored, replays, opening, version = [], [], {}, info["formula_version"]
    for repeat in range(1, info["repeats"] + 1):
        for scenario in scenarios:
            path = session_file(folder, scenario.id, repeat)
            if not path.exists():
                continue
            session = json.loads(path.read_text())
            again = replayed(session, score, with_judge, chat)
            stored.append(row_for(scenario, session, repeat))
            replays.append(row_for(scenario, again, repeat))
            if session["kind"] == "council":
                version = again["scoring"]["formula_version"]
                opening[f"{scenario.id}-r{repeat}"] = rescore(session, score, rounds=1)["verdict"]
    return {"info": info, "formula_version": version, "stored": stored, "replayed": replays, "opening": opening}


def with_score(row: dict) -> str:
    """Example: "Buy 7.6", or just "Declined"."""
    return LABELS[row["got"]] + (f" {row['score']}" if row["score"] is not None else "")


def render_comparison(result: dict) -> str:
    """Stored against replayed, scenario by scenario, then the replayed run's full report."""
    info, stored, replays, opening = result["info"], result["stored"], result["replayed"], result["opening"]
    version = result["formula_version"]
    before, after = summarize(stored), summarize(replays)
    councils = [row for row in replays if f"{row['id']}-r{row['repeat']}" in opening]
    first = lambda row: opening[f"{row['id']}-r{row['repeat']}"]
    lines = [
        f"# Replay of eval run {info['run_id']}",
        "",
        f"Scoring: stored formula v{info['formula_version']}, replayed with formula v{version}."
        " The debates are the same; only what code does with them changed.",
        "",
        f"- Agreement: stored {share(before['matched'], before['runs'])}, replayed {share(after['matched'], after['runs'])}",
        f"- Against the majority lean: stored {before['against_majority']}, replayed {after['against_majority']}"
        f" (of {after['councils']} councils)",
        "",
        "| Scenario | Expected | Stored | Replayed | After round 1 only |",
        "|---|---|---|---|---|",
    ]
    for old, new in zip(stored, replays):
        mark = "" if new["match"] else " (**no**)"
        after_one = LABELS[first(new)] if new in councils else ""
        lines.append(f"| {new['id']} | {LABELS[new['expected']]} | {with_score(old)} | {with_score(new)}{mark} | {after_one} |")
    changed = sum(first(row) != row["got"] for row in councils)
    right_after_one = sum(first(row) == row["expected"] for row in councils)
    right_final = sum(row["match"] for row in councils)
    lines += [
        "",
        f"Does the debate earn its time? The rebuttal rounds changed the verdict in {changed} of {len(councils)} councils."
        f" Matching the expected verdict: {right_after_one} after round 1 only, {right_final} after the whole debate.",
        "",
    ]
    replay_info = {**info, "run_id": f"{info['run_id']} (replayed with formula v{version})", "formula_version": version}
    return "\n".join(lines) + "\n" + render(replay_info, replays, after)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rescore (and optionally rejudge) a saved eval run without the council.")
    parser.add_argument("run_folder", type=Path, help="an eval run folder, such as evals/runs/<run id>")
    parser.add_argument("--judge", action="store_true", help="rerun the Judge on every council (uses the model)")
    parser.add_argument("--save", action="store_true", help="save replay.md and replay.json in the run folder")
    args = parser.parse_args(argv)

    result = replay_run(args.run_folder, with_judge=args.judge)
    text = render_comparison(result)
    print(text)
    if args.save:
        (args.run_folder / "replay.md").write_text(text)
        data = {key: result[key] for key in ("formula_version", "stored", "replayed", "opening")}
        (args.run_folder / "replay.json").write_text(json.dumps(data, indent=2))
        print(f"Saved to {args.run_folder / 'replay.md'}")


if __name__ == "__main__":
    main()
