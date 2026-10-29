"""The eval report: what one eval run says about the council, worked out from saved sessions.

Everything here is plain arithmetic on session dicts, the same JSON files the UI will read.
No model is called, so a report can be rebuilt at any time from a run's saved sessions
(for example after improving this file) without rerunning a single council.

Three layers:
- `row_for`: one scenario's session turned into one row of facts (verdict, leans, retries...).
- `summarize`: the rows added up into the headline numbers.
- `render`: the rows and the summary as a Markdown report, readable in a terminal or on GitHub.
"""

import re
from collections import Counter

from agents.roster import COUNCIL
from agents.schemas import CJK, CUT_OFF_SLACK, AgentRebuttal, AgentTake, Point, Rating, Ruling, is_cut_off, text_limit
from tools.registry import TOOLS

# Verdicts are ordered, so a miss is near (Wait instead of Buy) or far (Buy instead of Skip).
ORDER = {"buy": 0, "wait": 1, "skip": 2}
OUTCOMES = ["buy", "wait", "skip", "declined", "error"]

LIMITS = {
    "take": text_limit(AgentTake, "take"),
    "reason": text_limit(Rating, "reason"),
    "response": text_limit(AgentRebuttal, "response"),
    "summary": text_limit(Ruling, "summary"),
    "point": text_limit(Point, "point"),
    "would_change_verdict": text_limit(Ruling, "would_change_verdict"),
    "ruling": text_limit(Ruling, "ruling"),
}
# Ollama closes a string the moment it reaches max_length, and the reply still looks normal.
# So a text cut off that way sits right at its limit. The schemas share the same slack and the same
# test for a cut-off ending (agents/schemas.py), and since 10.25.2026 they send such a text back.
AT_LIMIT_SLACK = CUT_OFF_SLACK

# Voice check (a heuristic, so the report lists what it finds for a person to read).
# Only Future You speaks as the user. Another member writing "my daily commute" or "I use them"
# has slipped into the user's voice, while "my view" or "my estimate" is the member itself.
MY_WORD = re.compile(r"\bmy\s+(\w+)", re.IGNORECASE)
MEMBER_OWN = {
    "view", "take", "point", "points", "rating", "ratings", "score", "scores", "lean", "concern", "concerns",
    "focus", "analysis", "estimate", "estimates", "numbers", "calculation", "calculations", "confidence",
    "opinion", "position", "mind", "earlier", "original", "initial", "assessment", "main", "stance", "role",
    "job", "rubric", "read", "argument", "case", "advice", "recommendation", "own", "first", "last",
    "previous", "colleague", "colleagues", "fellow", "suggestion", "worry", "question", "side", "reasoning",
    "assumption", "assumptions",
}
# "my cost_per_use" or "my value_per_use" is the member naming its own tool or rubric item. The user never
# talks in these names, so they are read from the code instead of listed by hand.
MEMBER_OWN |= set(TOOLS) | {key for agent in COUNCIL for key in agent.ratings.model_fields}
USER_ACTION = re.compile(
    r"\bI(?:'m| am|'ve| have|'d| would)?\s+(?:use|used|using|commute|commuting|play|played|playing|own|bought|"
    r"watch|watched|listen|listened|travel|travelled|traveled)\b",
    re.IGNORECASE,
)
SPEAKS_TO_USER = re.compile(r"\byou(?:r|'re|'ll|'ve)?\b", re.IGNORECASE)
FUTURE_YOU = "Future You"
FUTURE_YOU_OPENING = "six months later"


# ---------------------------------------------------------------- one session -> one row

def outcome(session: dict) -> str:
    """buy, wait, skip, declined, or error (the council stopped, so there is no verdict)."""
    if session["kind"] in ("declined", "error"):
        return session["kind"]
    return session["scoring"]["verdict"]


def ok_turns(session: dict):
    """Every answered turn, in order, as (round number, turn)."""
    for round_ in session.get("rounds", []):
        for turn in round_["turns"]:
            if turn["status"] == "ok":
                yield round_["number"], turn


def final_leans(session: dict) -> dict[str, str]:
    """Each member's lean in its last good turn: the same replies scoring used."""
    return {turn["agent"]: turn["take_or_rebuttal"]["lean"] for _, turn in ok_turns(session)}


def opening_leans(session: dict) -> dict[str, str]:
    return {turn["agent"]: turn["take_or_rebuttal"]["lean"] for number, turn in ok_turns(session) if number == 1}


def majority(leans) -> str | None:
    """The lean held by more than half of the members, if there is one. 2-2 has none."""
    leans = list(leans)
    if not leans:
        return None
    lean, count = Counter(leans).most_common(1)[0]
    return lean if count * 2 > len(leans) else None


def tally(leans) -> str:
    """Example: "2 buy, 2 wait"."""
    return ", ".join(f"{count} {lean}" for lean, count in Counter(leans).most_common())


def texts(session: dict):
    """Every text the model wrote that ended up in the session, as (where, field, text).
    A template ruling is left out: code wrote it, not the model."""
    for number, turn in ok_turns(session):
        reply, where = turn["take_or_rebuttal"], f"round {number}, {turn['agent']}"
        for field in ("take", "response"):
            if field in reply:
                yield where, field, reply[field]
        for name, rating in reply["ratings"].items():
            yield f"{where}, {name}", "reason", rating["reason"]
    judge = session.get("judge")
    if judge and not judge["fallback_used"]:
        for field in ("summary", "would_change_verdict", "ruling"):
            yield "Judge", field, judge[field]
        for side in ("strongest_for", "strongest_against"):
            yield f"Judge, {side}", "point", judge[side]["point"]


def at_limit(session: dict) -> list[dict]:
    """Texts that stopped at their max_length, which usually means the end was cut off.
    `cut_off` says whether the ending is broken (no end of sentence), the kind a viewer would notice."""
    found = []
    for where, field, text in texts(session):
        limit = LIMITS[field]
        if len(text) >= limit - AT_LIMIT_SLACK:
            found.append({"where": where, "field": field, "length": len(text), "limit": limit,
                          "cut_off": is_cut_off(text, limit), "text": text})
    return found


def not_english(session: dict) -> list[dict]:
    """Texts with Chinese characters in them: Qwen sometimes switches language mid-sentence."""
    return [{"where": where, "field": field, "text": text} for where, field, text in texts(session) if CJK.search(text)]


def voice_flags(session: dict) -> list[dict]:
    """Possible voice slips. A heuristic: the report lists them so a person can check."""
    flags = []
    for number, turn in ok_turns(session):
        reply, agent = turn["take_or_rebuttal"], turn["agent"]
        text = reply.get("take") or reply.get("response", "")
        where = f"round {number}, {agent}"
        if agent == FUTURE_YOU:
            if number == 1 and not text.strip(" \"'").lower().startswith(FUTURE_YOU_OPENING):
                flags.append({"where": where, "issue": 'take does not start with "Six months later,"', "text": text})
            if number == 1 and SPEAKS_TO_USER.search(text):
                flags.append({"where": where, "issue": 'says "you" instead of speaking as the user', "text": text})
            continue
        slips = [f"my {word}" for word in MY_WORD.findall(text) if word.lower() not in MEMBER_OWN]
        slips += USER_ACTION.findall(text)
        if slips:
            flags.append({"where": where, "issue": f"may speak as the user ({', '.join(slips)})", "text": text})
    return flags


def attempt_records(session: dict) -> list[dict]:
    """Every answer attempt by a council member, in every round (the Judge and intake are counted apart)."""
    return [
        attempt
        for round_ in session.get("rounds", [])
        for turn in round_["turns"]
        for attempt in turn["trace"].get("attempts", [])
    ]


def rejection_field(error: str) -> str:
    """The field a rejection was about, from "take: Value error, ..." it is "take".
    Grouping by field shows which rule the model trips over most. Broken JSON and rules
    about the whole reply come back as "input" from Pydantic."""
    head = (error or "unknown").split(": ", 1)[0]
    return head if head and " " not in head and head != "input" else "the reply as a whole"


def token_cap_hits(session: dict) -> int:
    """Model calls that hit their token cap (the reply was cut short by config's safety limit)."""
    calls = [
        call
        for round_ in session.get("rounds", [])
        for turn in round_["turns"]
        for call in [*turn["trace"].get("attempts", []), *turn["trace"].get("model_calls", [])]
    ]
    if session.get("judge"):
        calls += session["judge"]["trace"].get("attempts", [])
    return sum(bool(call.get("cut_off")) for call in calls)


def row_for(scenario, session: dict, repeat: int = 1) -> dict:
    """One scenario's result as plain facts. `scenario` is an evals.scenarios.Scenario."""
    got = outcome(session)
    expected = scenario.expected
    leans = final_leans(session)
    lean_values = list(leans.values())
    lean_majority = majority(lean_values)
    is_council = got in ORDER
    turns = [turn for round_ in session.get("rounds", []) for turn in round_["turns"]]
    attempts = attempt_records(session)
    rejected = [attempt for attempt in attempts if not attempt["ok"]]
    judge = session.get("judge")
    intake = session.get("intake") or {}
    category = intake.get("category")
    opening_majority = majority(opening_leans(session).values())
    changes = [turn["changes"] for turn in turns if turn.get("changes")]

    return {
        "id": scenario.id,
        "repeat": repeat,
        "expected": expected,
        "got": got,
        "match": got == expected,
        # Steps apart on Buy, Wait, Skip. None when either side is a decline or an error.
        "distance": abs(ORDER[got] - ORDER[expected]) if is_council and expected in ORDER else None,
        "score": session["scoring"]["score"] if is_council else None,
        "leans": leans,
        "tally": tally(lean_values),
        "majority": lean_majority,
        # A lean rail held the verdict at Wait 30 days (scoring v2 and later; older sessions have no rail).
        "rail": session["scoring"].get("rail") if is_council else None,
        "against_majority": bool(is_council and lean_majority and got != lean_majority),
        "against_every_lean": bool(is_council and lean_values and got not in lean_values),
        "opening_majority": opening_majority,
        "majority_flipped": bool(is_council and opening_majority != lean_majority),
        "intake_ok": intake.get("ok"),
        "guard_triggered": bool((session.get("guard") or {}).get("triggered")),  # instructions set aside
        "category_expected": scenario.category,
        "category_got": category,
        # Checked only when the scenario names one category and the intake accepted it as a gadget.
        "category_match": category == scenario.category if scenario.category and got != "declined" else None,
        "rounds": len(session.get("rounds", [])),
        "tiebreak": any(round_["kind"] == "tiebreak" for round_ in session.get("rounds", [])),
        "turns": len(turns),
        "failed_turns": sum(turn["status"] == "failed" for turn in turns),
        "rejected_attempts": len(rejected),
        "rejections": dict(Counter(rejection_field(attempt["error"]) for attempt in rejected)),
        "rejection_examples": {rejection_field(a["error"]): a["error"] for a in reversed(rejected)},
        "judge_rejected": sum(not a["ok"] for a in judge["trace"].get("attempts", [])) if judge else 0,
        "judge_fallback": bool(judge and judge["fallback_used"]),
        "token_cap_hits": token_cap_hits(session),
        "at_limit": at_limit(session),
        "not_english": not_english(session),
        "voice_flags": voice_flags(session),
        "changed_minds": sum(bool(change.get("changed_mind")) for change in changes),
        "scores_moved": sum(change.get("scores_moved", 0) for change in changes),
        "seconds": session.get("timing", {}).get("total_seconds", 0),
        "error": session.get("error"),
    }


# ---------------------------------------------------------------- rows -> headline numbers

def summarize(rows: list[dict]) -> dict:
    councils = [row for row in rows if row["got"] in ORDER]
    graded = [row for row in rows if row["expected"] in ORDER]  # scenarios that expect a verdict
    turns = sum(row["turns"] for row in rows)
    rejected = sum(row["rejected_attempts"] for row in rows)
    category_checked = [row for row in rows if row["category_match"] is not None]
    seconds = [row["seconds"] for row in councils]

    confusion = {expected: {got: 0 for got in OUTCOMES} for expected in ["buy", "wait", "skip", "declined"]}
    for row in rows:
        confusion[row["expected"]][row["got"]] += 1

    reasons = Counter()
    for row in rows:
        reasons.update(row["rejections"])
    examples = {}
    for row in rows:
        examples.update(row["rejection_examples"])

    by_id = {}
    for row in rows:
        by_id.setdefault(row["id"], []).append(row["got"])
    repeated = {scenario: got for scenario, got in by_id.items() if len(got) > 1}

    return {
        "runs": len(rows),
        "scenarios": len(by_id),
        "matched": sum(row["match"] for row in rows),
        "verdicts_matched": sum(row["match"] for row in graded),
        "verdicts_expected": len(graded),
        "near_misses": sum(row["distance"] == 1 for row in graded),
        "far_misses": sum(row["distance"] == 2 for row in graded),
        "declines_right": sum(row["match"] for row in rows if row["expected"] == "declined"),
        "declines_expected": sum(row["expected"] == "declined" for row in rows),
        "wrongly_declined": sum(row["got"] == "declined" for row in graded),
        "errors": sum(row["got"] == "error" for row in rows),
        "guard_triggered": sum(row["guard_triggered"] for row in rows),
        "guard_scenarios": sorted({row["id"] for row in rows if row["guard_triggered"]}),
        "category_right": sum(row["category_match"] for row in category_checked),
        "category_checked": len(category_checked),
        "confusion": confusion,
        "councils": len(councils),
        "held_by_rail": sum(bool(row["rail"]) for row in rows),
        "against_majority": sum(row["against_majority"] for row in rows),
        "against_every_lean": sum(row["against_every_lean"] for row in rows),
        "majority_flipped": sum(row["majority_flipped"] for row in rows),
        "changed_minds": sum(row["changed_minds"] for row in rows),
        "scores_moved": sum(row["scores_moved"] for row in rows),
        "tiebreaks": sum(row["tiebreak"] for row in rows),
        "turns": turns,
        "rejected_attempts": rejected,
        "rejected_per_turn": round(rejected / turns, 2) if turns else 0.0,
        "failed_turns": sum(row["failed_turns"] for row in rows),
        "judge_rejected": sum(row["judge_rejected"] for row in rows),
        "judge_fallbacks": sum(row["judge_fallback"] for row in rows),
        "token_cap_hits": sum(row["token_cap_hits"] for row in rows),
        "texts_at_limit": sum(len(row["at_limit"]) for row in rows),
        "texts_cut_off": sum(item["cut_off"] for row in rows for item in row["at_limit"]),
        "texts_not_english": sum(len(row["not_english"]) for row in rows),
        "voice_flags": sum(len(row["voice_flags"]) for row in rows),
        "rejections": dict(reasons.most_common()),
        "rejection_examples": examples,
        "seconds_average": round(sum(seconds) / len(seconds), 1) if seconds else 0.0,
        "seconds_min": min(seconds, default=0.0),
        "seconds_max": max(seconds, default=0.0),
        "seconds_total": round(sum(row["seconds"] for row in rows), 1),
        # Scenarios run more than once: how many came out the same every time.
        "repeated": len(repeated),
        "stable": sum(len(set(got)) == 1 for got in repeated.values()),
    }


# ---------------------------------------------------------------- the report people read

LABELS = {"buy": "Buy", "wait": "Wait", "skip": "Skip", "declined": "Declined", "error": "Error"}


def minutes(seconds: float) -> str:
    """Example: 215 -> "3m 35s"."""
    whole = round(seconds)
    return f"{whole // 60}m {whole % 60:02d}s" if whole >= 60 else f"{whole}s"


def share(part: int, whole: int) -> str:
    return f"{part} of {whole} ({round(100 * part / whole)}%)" if whole else "0 of 0"


def clip(text: str, length: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 3] + "..."


def render(info: dict, rows: list[dict], summary: dict) -> str:
    """The report as Markdown. `info` describes the run (id, model, formula version, dates)."""
    s = summary
    lines = [
        f"# Eval run {info['run_id']}",
        "",
        f"Model `{info['model']}` · scoring formula v{info['formula_version']} · scenarios {info['scenarios_version']}"
        f" · {s['scenarios']} scenarios, {s['runs']} runs ({s['councils']} full councils) · {minutes(s['seconds_total'])} in all",
        f"Started {info['started_at']}" + (f" · finished {info['finished_at']}" if info.get("finished_at") else " · not finished"),
        "",
        "## Headline",
        "",
        f"- **Agreement with the expected outcome: {share(s['matched'], s['runs'])}**",
        f"- Buy, Wait, Skip scenarios: {share(s['verdicts_matched'], s['verdicts_expected'])} right;"
        f" {s['near_misses']} near misses (one step off), {s['far_misses']} far misses (Buy against Skip)",
        f"- Intake: non-gadgets declined {share(s['declines_right'], s['declines_expected'])};"
        f" gadgets wrongly declined: {s['wrongly_declined']}; category right {share(s['category_right'], s['category_checked'])}",
        f"- Verdict against the council: {s['against_majority']} against the majority lean,"
        f" {s['against_every_lean']} against every member's lean (of {s['councils']} councils)",
    ]
    if s["held_by_rail"]:
        lines.append(f"- Verdicts held at Wait 30 days by a lean rail (the score pointed to Buy or Skip, no member leaned that way):"
                     f" {s['held_by_rail']} of {s['councils']} councils")
    if s["errors"]:
        lines.append(f"- Councils that stopped with an error: {s['errors']}")
    if s["guard_triggered"]:
        lines.append(f"- Instructions set aside by the injection guard: {s['guard_triggered']}"
                     f" ({', '.join(s['guard_scenarios'])})")
    if s["repeated"]:
        lines.append(f"- Same outcome every time: {s['stable']} of {s['repeated']} repeated scenarios")

    lines += [
        "",
        "## Expected against what the council said",
        "",
        "| Expected | " + " | ".join(LABELS[o] for o in OUTCOMES) + " |",
        "|---|" + "---|" * len(OUTCOMES),
    ]
    for expected, counts in s["confusion"].items():
        if any(counts.values()):
            lines.append(f"| {LABELS[expected]} | " + " | ".join(str(counts[o] or "") for o in OUTCOMES) + " |")

    lines += [
        "",
        "## Reliability",
        "",
        f"- Rejected answers: {s['rejected_attempts']} in {s['turns']} turns ({s['rejected_per_turn']} per turn);"
        f" turns that failed every attempt: {s['failed_turns']}",
        f"- Judge: {s['judge_rejected']} rejected answers, {s['judge_fallbacks']} template fallbacks",
        f"- Replies cut short by the token cap: {s['token_cap_hits']}; texts stopped at their length limit: {s['texts_at_limit']}"
        f" ({s['texts_cut_off']} cut off mid-sentence); texts with Chinese characters: {s['texts_not_english']}",
        f"- Possible voice slips (a heuristic, read them below): {s['voice_flags']}",
        "",
        "## The debate",
        "",
        f"- Tiebreak rounds: {s['tiebreaks']} of {s['councils']} councils",
        f"- After the opening round: {s['changed_minds']} leans changed, {s['scores_moved']} scores moved;"
        f" the majority lean changed in {s['majority_flipped']} councils",
        f"- Time per council: {minutes(s['seconds_average'])} on average"
        f" ({minutes(s['seconds_min'])} to {minutes(s['seconds_max'])})" if s["councils"] else "- Time per council: no full council ran",
        "",
        "## Every scenario",
        "",
        "| Scenario | Expected | Got | Score | Final leans | Rounds | Retries | Time |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        mark = "yes" if row["match"] else "**no**"
        name = row["id"] + (f" (run {row['repeat']})" if s["repeated"] else "")
        score = "" if row["score"] is None else f"{row['score']}"
        lines.append(
            f"| {name} | {LABELS[row['expected']]} | {LABELS[row['got']]} ({mark}) | {score} | {row['tally']} |"
            f" {row['rounds'] or ''} | {row['rejected_attempts'] + row['judge_rejected'] or ''} | {minutes(row['seconds'])} |"
        )

    if s["rejections"]:
        lines += ["", "## What the model got rejected for", ""]
        for field, count in s["rejections"].items():
            lines.append(f"- `{field}`: {count} (for example: {clip(s['rejection_examples'][field])})")

    details = [(row, item) for row in rows for item in row["at_limit"]]
    if details:
        lines += ["", "## Texts that stopped at their length limit", ""]
        for row, item in details:
            broken = ", cut off" if item["cut_off"] else ""
            lines.append(f"- {row['id']}, {item['where']}, `{item['field']}` ({item['length']} of {item['limit']}{broken}): "
                         f"...{clip(item['text'][-90:], 90)}")

    flags = [(row, item) for row in rows for item in row["voice_flags"]]
    if flags:
        lines += ["", "## Possible voice slips", ""]
        for row, item in flags:
            lines.append(f"- {row['id']}, {item['where']}: {item['issue']}. \"{clip(item['text'])}\"")

    errors = [row for row in rows if row["error"]]
    if errors:
        lines += ["", "## Councils that stopped", ""]
        lines += [f"- {row['id']}: {row['error']}" for row in errors]

    return "\n".join(lines) + "\n"
