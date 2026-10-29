"""Phase 5 tests, step 5: scoring v2. Weights, cut-offs, the two lean rails, what the Judge is told,
and that the design script and scoring.py agree. None of them call the real model.

Run with:  .venv/bin/python -m unittest -v
"""

import json
import random
import unittest
from unittest import mock

import scoring
from agents import judge
from agents.alternatives_hunter import ALTERNATIVES_HUNTER
from agents.analyst import ANALYST
from agents.budget_guardian import BUDGET_GUARDIAN
from agents.future_you import FUTURE_YOU
from agents.roster import COUNCIL
from agents.schemas import Ruling
from debate import final_replies
from evals import design_v2, report
from tests.helpers import FakeChat
from tests.test_phase4 import take_for
from tests.test_phase4_council import judge_reply, judged_debate
from tests.test_phase5_evals import council, scenario

AGENTS = {agent.name: agent for agent in COUNCIL}


def reply(agent, scores, lean="wait"):
    """A validated take for any agent with these three rating scores and this lean."""
    data = take_for(agent, lean=lean)
    for name, value in zip(agent.ratings.model_fields, scores):
        data["ratings"][name]["score"] = value
    return agent.take_schema.model_validate(data)


def council_of(score, *leans):
    """A whole council whose every rating is `score`, with these leans in speaking order."""
    return {agent.name: reply(agent, (score,) * 3, lean) for agent, lean in zip(COUNCIL, leans)}


class Weights(unittest.TestCase):
    def test_every_rubric_item_has_a_weight_and_nothing_else_does(self):
        rubric = {name for agent in COUNCIL for name in agent.ratings.model_fields}
        self.assertEqual(set(scoring.WEIGHTS), rubric)

    def test_only_cost_of_waiting_is_left_out(self):
        self.assertEqual({name for name, weight in scoring.WEIGHTS.items() if weight == 0}, {"cost_of_waiting"})
        self.assertEqual({weight for weight in scoring.WEIGHTS.values()}, {0, 1})

    def test_a_rating_with_no_weight_is_refused_not_guessed(self):
        final = {"The Analyst": reply(ANALYST, (5, 5, 5))}
        with mock.patch.dict(scoring.WEIGHTS):
            del scoring.WEIGHTS["longevity"]
            with self.assertRaises(ValueError) as error:
                scoring.score(final)
        self.assertIn("longevity", str(error.exception))


class CostOfWaiting(unittest.TestCase):
    def test_it_is_rated_and_shown_but_does_not_move_the_score(self):
        scores = []
        for waiting in (1, 5, 10):
            final = {"The Analyst": reply(ANALYST, (6, 6, 6)), "Budget Guardian": reply(BUDGET_GUARDIAN, (4, waiting, 4))}
            result = scoring.score(final)
            scores.append(result["score"])
            self.assertEqual(result["inputs"]["Budget Guardian"]["cost_of_waiting"], waiting)
        self.assertEqual(scores, [5.2, 5.2, 5.2])  # (18 + 4 + 4) / 5

    def test_the_result_says_what_it_did_not_count(self):
        result = scoring.score(council_of(5, "wait", "wait", "wait", "wait"))
        self.assertEqual(result["not_counted"], ["cost_of_waiting"])
        self.assertEqual(result["ratings_counted"], 11)  # 12 rated, 1 not counted

    def test_a_council_without_the_guardian_counts_every_rating(self):
        result = scoring.score({"The Analyst": reply(ANALYST, (5, 5, 5)), "Future You": reply(FUTURE_YOU, (5, 5, 5))})
        self.assertEqual((result["ratings_counted"], result["not_counted"]), (6, []))

    def test_agent_averages_leave_it_out_too(self):
        final = {"Budget Guardian": reply(BUDGET_GUARDIAN, (2, 10, 4)), "The Analyst": reply(ANALYST, (6, 6, 6))}
        self.assertEqual(scoring.score(final)["agent_averages"], {"Budget Guardian": 3.0, "The Analyst": 6.0})


class CutOffs(unittest.TestCase):
    def test_the_cut_offs_sit_where_the_design_put_them(self):
        self.assertEqual((scoring.BUY_AT, scoring.WAIT_AT), (5.5, 4.5))

    def test_the_boundaries(self):
        cases = {5.5: "buy", 5.4: "wait", 4.5: "wait", 4.4: "skip"}
        for value, verdict in cases.items():
            with self.subTest(score=value):
                self.assertEqual(scoring.verdict_for(value), verdict)

    def test_the_verdict_is_picked_from_the_rounded_score(self):
        # 11 ratings count. A total of 60 is 5.4545..., shown as 5.5, so the card must say Buy;
        # 59 is 5.3636..., shown as 5.4, so it must say Wait. Every member leans Buy so no rail interferes.
        def council_totalling(hunter):
            rows = [(6, 6, 6), (5, 5, 5), (5, 1, 5), hunter]  # the 1 is cost_of_waiting, not counted
            return {agent.name: reply(agent, scores, "buy") for agent, scores in zip(COUNCIL, rows)}

        shown_as_55 = scoring.score(council_totalling((6, 6, 5)))
        self.assertEqual((shown_as_55["score"], shown_as_55["verdict"]), (5.5, "buy"))
        shown_as_54 = scoring.score(council_totalling((6, 5, 5)))
        self.assertEqual((shown_as_54["score"], shown_as_54["verdict"]), (5.4, "wait"))


class Rails(unittest.TestCase):
    def test_a_buy_score_with_nobody_leaning_buy_is_held_at_wait(self):
        result = scoring.score(council_of(8, "wait", "wait", "skip", "wait"))
        self.assertEqual(result["score"], 8.0)  # the score is not touched
        self.assertEqual((result["score_verdict"], result["verdict"]), ("buy", "wait"))
        self.assertEqual(result["rail"], "buy_needs_a_buy_lean")
        self.assertIn("no member leaned Buy", result["rail_note"])
        self.assertEqual(result["verdict_label"], "Wait 30 days")

    def test_one_member_leaning_buy_is_enough(self):
        result = scoring.score(council_of(8, "buy", "wait", "wait", "wait"))
        self.assertEqual((result["verdict"], result["rail"], result["rail_note"]), ("buy", None, None))

    def test_a_skip_score_with_nobody_leaning_skip_is_held_at_wait(self):
        result = scoring.score(council_of(2, "wait", "wait", "buy", "wait"))
        self.assertEqual((result["score_verdict"], result["verdict"]), ("skip", "wait"))
        self.assertEqual(result["rail"], "skip_needs_a_skip_lean")
        self.assertIn("no member leaned Skip", result["rail_note"])

    def test_one_member_leaning_skip_is_enough(self):
        result = scoring.score(council_of(2, "wait", "skip", "wait", "wait"))
        self.assertEqual((result["verdict"], result["rail"]), ("skip", None))

    def test_a_wait_score_is_never_touched(self):
        for leans in (("buy", "buy", "buy", "buy"), ("skip", "skip", "skip", "skip"), ("wait",) * 4):
            with self.subTest(leans=leans):
                result = scoring.score(council_of(5, *leans))
                self.assertEqual((result["verdict"], result["rail"]), ("wait", None))

    def test_the_rails_only_ever_move_a_verdict_to_wait(self):
        for verdict in ("buy", "wait", "skip"):
            for leans in ([], ["buy"], ["skip"], ["wait"], ["buy", "skip"], ["buy", "wait", "skip"]):
                with self.subTest(verdict=verdict, leans=leans):
                    final, _ = scoring.apply_rails(verdict, leans)
                    self.assertIn(final, (verdict, "wait"))

    def test_a_council_that_all_leans_wait_can_only_say_wait(self):
        for value in range(1, 11):
            with self.subTest(every_rating=value):
                self.assertEqual(scoring.score(council_of(value, "wait", "wait", "wait", "wait"))["verdict"], "wait")

    def test_no_verdict_is_one_that_no_member_argued_for(self):
        rng = random.Random(11)
        for _ in range(300):
            names = rng.sample(list(AGENTS), rng.randint(2, 4))
            final = {name: reply(AGENTS[name], [rng.randint(1, 10) for _ in range(3)], rng.choice(["buy", "wait", "skip"]))
                     for name in names}
            result = scoring.score(final)
            if result["verdict"] != "wait":
                self.assertIn(result["verdict"], result["leans"].values())

    def test_every_verdict_can_be_reached(self):
        self.assertEqual(scoring.score(council_of(8, "buy", "wait", "wait", "wait"))["verdict"], "buy")
        self.assertEqual(scoring.score(council_of(5, "wait", "wait", "wait", "wait"))["verdict"], "wait")
        self.assertEqual(scoring.score(council_of(2, "wait", "skip", "wait", "wait"))["verdict"], "skip")

    def test_the_result_is_plain_data_that_can_be_saved(self):
        result = scoring.score(council_of(8, "buy", "wait", "skip", "wait"))
        self.assertEqual(json.loads(json.dumps(result)), result)
        self.assertEqual(result["leans"]["Budget Guardian"], "skip")


class DesignScript(unittest.TestCase):
    """evals/design_v2.py is the showcase of how the formula was chosen. If it drifts from scoring.py it lies."""

    def test_its_v2_formula_agrees_with_scoring_py(self):
        formula = design_v2.FORMULAS["average, cost_of_waiting at 0"]
        rng = random.Random(5)
        for _ in range(300):
            names = rng.sample(list(AGENTS), rng.randint(2, 4))
            final = {name: reply(AGENTS[name], [rng.randint(1, 10) for _ in range(3)], rng.choice(["buy", "wait", "skip"]))
                     for name in names}
            row = {"final": {name: {"ratings": {k: v.score for k, v in r.ratings}, "lean": r.lean, "confidence": r.confidence}
                             for name, r in final.items()}}
            ours = design_v2.verdicts([row], formula, design_v2.rail_leans, scoring.BUY_AT, scoring.WAIT_AT)[0]
            self.assertEqual(ours, scoring.score(final)["verdict"], row)


class JudgeIsTold(unittest.TestCase):
    def held_back(self):
        debate, _ = judged_debate()
        result = scoring.score(council_of(8, "wait", "wait", "wait", "wait"))
        return debate, result

    def test_the_prompt_carries_the_rule_that_held_the_verdict(self):
        debate, result = self.held_back()
        prompt = judge.build_prompt(debate, result)
        self.assertIn(f"Rule applied: {result['rail_note']}", prompt)
        self.assertIn("Verdict: Wait 30 days", prompt)
        self.assertIn("not counting cost of waiting", prompt)

    def test_the_prompt_has_no_rule_line_when_no_rail_held(self):
        debate, result = judged_debate()
        self.assertNotIn("Rule applied", judge.build_prompt(debate, result))

    def test_the_system_prompt_asks_for_it_without_quoting_an_example(self):
        self.assertIn("names a rule that held the verdict", judge.SYSTEM_PROMPT)
        self.assertNotIn("no member leaned Buy", judge.SYSTEM_PROMPT)  # the model copies example lines word for word

    def test_the_rule_note_numbers_are_ones_the_judge_may_use(self):
        # The Judge may only write numbers it was given; the note and the formula are in its prompt.
        debate, result = self.held_back()
        ruling = judge_reply(ruling="The score reached 8.0, but no member leaned Buy, so it holds at 30 days.")
        _, trace, _ = judge.rule(debate, result, chat=FakeChat([ruling]))
        self.assertEqual([a["ok"] for a in trace["attempts"]], [True])

    def test_the_fallback_ruling_names_the_rail(self):
        final = final_replies(judged_debate()[0])
        for rail, expected in (("buy_needs_a_buy_lean", "no member leaned Buy"), ("skip_needs_a_skip_lean", "no member leaned Skip")):
            with self.subTest(rail=rail):
                ruling = judge.fallback_ruling({"score": 5.8, "verdict": "wait", "rail": rail}, final)
                self.assertIn(expected, ruling.ruling)
                self.assertIn("5.8 out of 10", ruling.ruling)
                self.assertLessEqual(len(ruling.ruling), 160)
                Ruling.model_validate(ruling.model_dump())  # still a valid ruling

    def test_a_plain_wait_keeps_the_plain_fallback(self):
        final = final_replies(judged_debate()[0])
        ruling = judge.fallback_ruling({"score": 5.0, "verdict": "wait", "rail": None}, final)
        self.assertIn("give it 30 days and see if you still want it", ruling.ruling)


class Report(unittest.TestCase):
    def test_a_row_records_the_rail_and_the_summary_counts_it(self):
        held = report.row_for(scenario("buy"), council())  # the scripted council is held at Wait by a rail
        self.assertEqual(held["rail"], "buy_needs_a_buy_lean")
        plain = council()
        plain["scoring"]["rail"] = None
        free = report.row_for(scenario("wait", id="other"), plain)
        self.assertIsNone(free["rail"])
        summary = report.summarize([held, free])
        self.assertEqual(summary["held_by_rail"], 1)
        text = report.render({"run_id": "t", "model": "m", "formula_version": 2, "scenarios_version": "v1.0",
                              "started_at": "now", "finished_at": "later"}, [held, free], summary)
        self.assertIn("held at Wait 30 days by a lean rail", text)
        self.assertIn(": 1 of 2 councils", text)

    def test_an_older_session_without_a_rail_still_reads(self):
        old = council()
        del old["scoring"]["rail"]
        self.assertIsNone(report.row_for(scenario("wait"), old)["rail"])
        self.assertEqual(report.summarize([report.row_for(scenario("wait"), old)])["held_by_rail"], 0)


if __name__ == "__main__":
    unittest.main()
