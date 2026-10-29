"""Phase 5 step 4: the numbers behind the scoring v2 design, from saved eval runs only.

No model calls. It reads every saved council of the chosen model from `evals/runs/` and prints:
1. which rubric items separate Buy from Skip purchases (and which don't),
2. what the members' leans and confidence tell us,
3. how candidate formulas and "rails" do, with cut-offs fitted on all councils (optimistic) and
   leave-one-scenario-out (honest: each purchase is judged by cut-offs tuned without it).

Run from the project folder:
  .venv/bin/python -m evals.design_v2                  every saved qwen2.5:14b council
  .venv/bin/python -m evals.design_v2 --model qwen2.5:7b

The design it led to is in PROGRESS.md and docs/build-log.md, and scoring.py (formula v2) is built from it.
Section 4 describes the design at scoring.py's own cut-offs; a test checks that the formula here and scoring.score agree.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, pstdev

import scoring

RUNS = Path(__file__).parent / "runs"
ORDER = {"skip": 0, "wait": 1, "buy": 2}
ITEMS = ["value_per_use", "longevity", "upgrade_gap", "six_month_glow", "want_vs_reason", "use_reality",
         "price_for_the_problem", "cost_of_waiting", "better_than_keeping_it", "worth_full_price",
         "release_timing", "ecosystem_freedom"]
CLASSES = ("buy", "wait", "skip")
GRID = [round(x * 0.1, 1) for x in range(25, 80)]


# ---------------------------------------------------------------- saved sessions -> flat rows

def load(model: str) -> list[dict]:
    """One row per council: expected verdict, each member's final ratings, lean and confidence
    (the same replies scoring uses: the last valid one per member). The injection scenario is
    skipped where the guard was not there yet, since the council then read the injected order."""
    rows = []
    for folder in sorted(RUNS.glob(f"*-{model.replace(':', '-')}-v*")):
        run = json.loads((folder / "run.json").read_text())
        expected = {s["id"]: s["expected"] for s in run["scenarios"]}
        for path in sorted((folder / "sessions").glob("*.json")):
            session = json.loads(path.read_text())
            if session.get("kind") != "council":
                continue
            scenario, repeat = path.stem.rsplit("-r", 1)
            if scenario == "injection-gaming-laptop" and not (session.get("guard") or {}).get("triggered"):
                continue
            final = {}
            for round_ in session["rounds"]:
                for turn in round_["turns"]:
                    if turn["status"] == "ok":
                        reply = turn["take_or_rebuttal"]
                        final[turn["agent"]] = {"ratings": {k: v["score"] for k, v in reply["ratings"].items()},
                                                "lean": reply["lean"], "confidence": reply["confidence"]}
            rows.append({"run": run["run_id"], "id": scenario, "repeat": int(repeat), "expected": expected[scenario],
                         "v1": session["scoring"]["verdict"], "final": final})
    return rows


def items_of(row: dict) -> dict:
    return {k: v for rec in row["final"].values() for k, v in rec["ratings"].items()}


def leans_of(row: dict) -> list[str]:
    return [rec["lean"] for rec in row["final"].values()]


# ---------------------------------------------------------------- formulas: a council -> a number

def weighted(row: dict, weights: dict) -> float:
    items = items_of(row)
    return sum(weights[k] * v for k, v in items.items()) / sum(weights[k] for k in items)


def per_member(row: dict, weights: dict) -> float:
    """Each member's weighted rubric average, then the plain mean over members: one member, one say."""
    averages = []
    for rec in row["final"].values():
        total = sum(weights[k] for k in rec["ratings"])
        if total:
            averages.append(sum(weights[k] * v for k, v in rec["ratings"].items()) / total)
    return mean(averages)


EQUAL = {k: 1 for k in ITEMS}
NO_COST_OF_WAITING = {k: (0 if k == "cost_of_waiting" else 1) for k in ITEMS}
STRONG = {"value_per_use": 2, "longevity": 1, "upgrade_gap": 2, "six_month_glow": 2, "want_vs_reason": 2,
          "use_reality": 2, "price_for_the_problem": 1, "cost_of_waiting": 0, "better_than_keeping_it": 2,
          "worth_full_price": 1, "release_timing": 1, "ecosystem_freedom": 1}
LEAN_POINTS = {"buy": 8.5, "wait": 5.5, "skip": 2.5}

FORMULAS = {
    "v1: plain average": lambda r: weighted(r, EQUAL),
    "average, cost_of_waiting at 0": lambda r: weighted(r, NO_COST_OF_WAITING),
    "weighted 2/1/0 by signal": lambda r: weighted(r, STRONG),
    "per member, weighted 2/1/0": lambda r: per_member(r, STRONG),
    "half ratings, half lean points": lambda r: (weighted(r, NO_COST_OF_WAITING) + mean(LEAN_POINTS[l] for l in leans_of(r))) / 2,
}


# ---------------------------------------------------------------- rails: a verdict and the leans -> a verdict

def rail_none(verdict: str, leans: list[str]) -> str:
    return verdict


def rail_leans(verdict: str, leans: list[str]) -> str:
    """Buy needs a member leaning Buy; Skip needs a member leaning Skip. Otherwise the verdict is Wait."""
    if verdict == "buy" and "buy" not in leans:
        return "wait"
    if verdict == "skip" and "skip" not in leans:
        return "wait"
    return verdict


def rail_majority(verdict: str, leans: list[str]) -> str:
    """Three or more members who agree decide; otherwise the score does."""
    lean, count = Counter(leans).most_common(1)[0]
    return lean if count >= 3 else verdict


RAILS = {"no rails": rail_none, "lean rails": rail_leans, "majority of 3 wins": rail_majority}


def verdicts(rows, formula, rail, buy_at, wait_at) -> list[str]:
    out = []
    for row in rows:
        value = round(formula(row) + 1e-9, 1)
        raw = "buy" if value >= buy_at else ("wait" if value >= wait_at else "skip")
        out.append(rail(raw, leans_of(row)))
    return out


def right(rows, got) -> int:
    return sum(v == row["expected"] for row, v in zip(rows, got))


def fit(rows, formula, rail):
    """The cut-offs with the most agreement on these rows, and the plateau: every pair within one council of it."""
    results = {(b, w): right(rows, verdicts(rows, formula, rail, b, w)) for b in GRID for w in GRID if w < b}
    top = max(results.values())
    plateau = [pair for pair, n in results.items() if n >= top - 1]
    return max(results, key=results.get), top, plateau, results


def leave_one_scenario_out(rows, formula, rail) -> int:
    """Fit the cut-offs without one scenario, judge that scenario's councils with them; over every scenario."""
    total = 0
    for scenario in {row["id"] for row in rows}:
        train = [row for row in rows if row["id"] != scenario]
        test = [row for row in rows if row["id"] == scenario]
        (buy_at, wait_at), _, _, _ = fit(train, formula, rail)
        total += right(test, verdicts(test, formula, rail, buy_at, wait_at))
    return total


def describe(rows, got) -> dict:
    by_class = {c: [0, 0] for c in CLASSES}
    far = against_majority = against_every = 0
    for row, v in zip(rows, got):
        by_class[row["expected"]][1] += 1
        by_class[row["expected"]][0] += v == row["expected"]
        far += abs(ORDER[v] - ORDER[row["expected"]]) == 2
        leans = leans_of(row)
        lean, count = Counter(leans).most_common(1)[0]
        against_majority += count * 2 > len(leans) and v != lean
        against_every += v not in leans
    per_scenario = defaultdict(set)
    for row, v in zip(rows, got):
        per_scenario[row["id"]].add(v)
    return {"right": right(rows, got), "by_class": "/".join(str(by_class[c][0]) for c in CLASSES), "far": far,
            "against_majority": against_majority, "against_every": against_every,
            "same_every_time": f"{sum(len(s) == 1 for s in per_scenario.values())}/{len(per_scenario)}"}


# ---------------------------------------------------------------- the report

def main(argv=None):
    parser = argparse.ArgumentParser(description="The numbers behind the scoring v2 design, from saved eval runs.")
    parser.add_argument("--model", default="qwen2.5:14b")
    parser.add_argument("--buy-at", type=float, default=scoring.BUY_AT, help="the Buy cut-off to describe in detail")
    parser.add_argument("--wait-at", type=float, default=scoring.WAIT_AT, help="the Skip cut-off to describe in detail")
    args = parser.parse_args(argv)

    rows = load(args.model)
    by_class = {c: [row for row in rows if row["expected"] == c] for c in CLASSES}
    print(f"{len(rows)} saved councils on {args.model} from {len({row['run'] for row in rows})} runs: "
          + ", ".join(f"{len(by_class[c])} expected {c}" for c in CLASSES))

    print("\n== 1. Rubric items: mean score by expected class, and how far Buy sits from Skip (in standard deviations) ==")
    print(f"{'item':24} {'Buy':>5} {'Wait':>5} {'Skip':>5} {'Buy-Skip/sd':>12} {'in order':>9}")
    for item in ITEMS:
        # A member that failed every attempt sat out, so its items are missing from that council.
        means = {c: mean(items_of(row)[item] for row in by_class[c] if item in items_of(row)) for c in CLASSES}
        sd = pstdev([items_of(row)[item] for row in rows if item in items_of(row)])
        in_order = means["buy"] > means["wait"] > means["skip"]
        print(f"{item:24} {means['buy']:5.2f} {means['wait']:5.2f} {means['skip']:5.2f} {(means['buy'] - means['skip']) / sd:12.2f} {'yes' if in_order else 'no':>9}")

    print("\n== 2. Leans and confidence ==")
    members = list(dict.fromkeys(agent for row in rows for agent in row["final"]))
    for agent in members:
        counts = {c: dict(Counter(row["final"][agent]["lean"] for row in by_class[c] if agent in row["final"])) for c in CLASSES}
        print(f"  {agent:20} " + "  ".join(f"{c}: {counts[c]}" for c in CLASSES))
    for c in CLASSES:
        any_buy = sum("buy" in leans_of(row) for row in by_class[c])
        any_skip = sum("skip" in leans_of(row) for row in by_class[c])
        print(f"  expected {c:5}: a Buy lean in {any_buy} of {len(by_class[c])} councils, a Skip lean in {any_skip}")
    confidence = Counter(rec["confidence"] for row in rows for rec in row["final"].values())
    print(f"  confidence over all final turns: {dict(sorted(confidence.items()))}")
    for lean in CLASSES:
        values = [rec["confidence"] for row in rows for rec in row["final"].values() if rec["lean"] == lean]
        print(f"  mean confidence behind a {lean} lean: {mean(values) if values else float('nan'):.2f} ({len(values)} turns)")

    print("\n== 3. Candidates: cut-offs fitted on every council (optimistic) and leave-one-scenario-out (honest) ==")
    print(f"{'formula':32} {'rails':20} {'fitted':>9} {'right':>6} {'plateau':>8} {'one-out':>8}  {'buy/wait/skip':>14} {'far':>4} {'vs maj':>7} {'vs all':>7} {'same':>6}")
    for fname, formula in FORMULAS.items():
        for rname, rail in RAILS.items():
            (buy_at, wait_at), top, plateau, _ = fit(rows, formula, rail)
            one_out = leave_one_scenario_out(rows, formula, rail)
            d = describe(rows, verdicts(rows, formula, rail, buy_at, wait_at))
            print(f"{fname:32} {rname:20} {buy_at:>4}/{wait_at:<4} {top:>3}/{len(rows)} {len(plateau):>8} {one_out:>4}/{len(rows)}  "
                  f"{d['by_class']:>14} {d['far']:>4} {d['against_majority']:>7} {d['against_every']:>7} {d['same_every_time']:>6}")

    print(f"\n== 4. The v2 design in detail: average with cost_of_waiting at 0, Buy from {args.buy_at}, Skip below {args.wait_at}, lean rails ==")
    formula, rail = FORMULAS["average, cost_of_waiting at 0"], rail_leans
    got = verdicts(rows, formula, rail, args.buy_at, args.wait_at)
    raw = verdicts(rows, formula, rail_none, args.buy_at, args.wait_at)
    print("  v1 as stored:", describe(rows, [row["v1"] for row in rows]))
    print("  v2:          ", describe(rows, got))
    print(f"  the rails changed {sum(a != b for a, b in zip(raw, got))} verdicts: {dict(Counter(f'{a} to {b}' for a, b in zip(raw, got) if a != b))}")
    _, _, plateau, results = fit(rows, formula, rail)
    print(f"  plateau: Buy cut-off {min(p[0] for p in plateau)} to {max(p[0] for p in plateau)}, Skip cut-off {min(p[1] for p in plateau)} to {max(p[1] for p in plateau)};"
          f" {args.buy_at}/{args.wait_at} gives {results.get((args.buy_at, args.wait_at))}, the best pair gives {max(results.values())}")
    for c in CLASSES:
        values = [formula(row) for row in by_class[c]]
        print(f"  v2 score, expected {c:5}: mean {mean(values):.2f}, {min(values):.1f} to {max(values):.1f}")
    print("  per run, v1 then v2:", "; ".join(
        f"{run_id[:15]} {sum(row['v1'] == row['expected'] for row in rows if row['run'] == run_id)} then "
        f"{sum(v == row['expected'] for row, v in zip(rows, got) if row['run'] == run_id)} of {sum(row['run'] == run_id for row in rows)}"
        for run_id in dict.fromkeys(row["run"] for row in rows)))
    print("  misses:")
    for row, v in zip(rows, got):
        if v != row["expected"]:
            print(f"    {row['run'][:15]} {row['id']} run {row['repeat']}: expected {row['expected']}, got {v}, score {formula(row):.2f}, leans {dict(Counter(leans_of(row)))}")
    print("  per scenario, mean v2 score and the verdict in each council:")
    per = defaultdict(list)
    for row, v in zip(rows, got):
        per[(row["expected"], row["id"])].append((formula(row), v))
    for (expected, scenario), values in sorted(per.items(), key=lambda kv: (-ORDER[kv[0][0]], -mean(x[0] for x in kv[1]))):
        print(f"    {expected:5} {scenario:26} {mean(x[0] for x in values):.2f}  {' '.join(v[0] for _, v in values)}")


if __name__ == "__main__":
    main()
