"""Phase 4 tests, milestone 4: the intake check, the scoring mechanics, the Judge, the tiebreak rule,
and run_council end to end. None of them call the real model.

Run with:  .venv/bin/python -m unittest -v
"""

import json
import unittest

from pydantic import ValidationError

import config
import scoring
from agents import intake, judge
from agents.alternatives_hunter import ALTERNATIVES_HUNTER
from agents.analyst import ANALYST
from agents.budget_guardian import BUDGET_GUARDIAN
from agents.future_you import FUTURE_YOU
from agents.roster import COUNCIL
from agents.council_agent import open_turn, rebuttal_turn
from agents.schemas import Intake, Ruling
from council import CouncilError, is_split, run_council
from debate import Debate, Round, Turn, final_replies, render_round
from tests.helpers import FakeChat, tool_request
from tests.test_phase4 import COST_ARGS, PURCHASE, take_for
from tests.test_phase4_debate import opening_replies, opening_round, rebuttal_for, rebuttal_replies


def intake_reply(gadget=True, category="audio", instructions=False) -> str:
    note = "Noise-cancelling headphones are an audio gadget." if gadget else "A leather sofa is furniture."
    return json.dumps({"note": note, "why_has_instructions": instructions, "is_tech_gadget": gadget,
                       "category": category if gadget else None})


def judge_reply(**changes) -> str:
    data = {
        "summary": "The council agreed the commute problem is real. They split on whether the price fits it.",
        "strongest_for": {"agent": "The Analyst", "point": "It gets used every single day on the commute."},
        "strongest_against": {"agent": "Budget Guardian", "point": "It is a lot of money for one problem."},
        "most_persuasive": "Budget Guardian",
        "would_change_verdict": "Learning that it would be used far less than planned.",
        "ruling": "Give it a month and see if the commute still bothers you as much.",
    }
    data.update(changes)
    return json.dumps(data)


def rebuttals_with(leans) -> list[str]:
    """One rebuttal per agent in speaking order, with the given leans."""
    replies = []
    for agent, lean in zip(COUNCIL, leans):
        target = next(other.name for other in COUNCIL if other.name != agent.name)
        replies.append(json.dumps(rebuttal_for(agent, [target], lean=lean)))
    return replies


def reply_with(agent, *scores):
    """A validated take whose three ratings have these scores."""
    data = take_for(agent)
    for name, value in zip(agent.ratings.model_fields, scores):
        data["ratings"][name]["score"] = value
    return agent.take_schema.model_validate(data)


class IntakeCheck(unittest.TestCase):
    def test_a_gadget_needs_a_category(self):
        with self.assertRaises(ValidationError):
            Intake(note="Headphones are audio gear.", why_has_instructions=False, is_tech_gadget=True, category=None)

    def test_something_that_is_not_a_gadget_has_no_category(self):
        result = Intake(note="A sofa is furniture.", why_has_instructions=False, is_tech_gadget=False, category="audio")
        self.assertIsNone(result.category)

    def test_it_runs_cold_and_short(self):
        fake = FakeChat([intake_reply()])
        result, record = intake.check_intake(PURCHASE, chat=fake)

        self.assertEqual((result.is_tech_gadget, result.category), (True, "audio"))
        self.assertTrue(record["ok"])
        options = fake.calls[0]["options"]
        self.assertEqual(options["temperature"], config.INTAKE_TEMPERATURE)
        self.assertEqual(options["num_predict"], config.MAX_INTAKE_TOKENS)

    def test_a_failed_check_assumes_a_gadget_and_says_so(self):
        result, record = intake.check_intake(PURCHASE, chat=FakeChat(["bad"] * config.MAX_ATTEMPTS))
        self.assertEqual((result.is_tech_gadget, result.category), (True, None))
        self.assertFalse(record["ok"])
        self.assertIn("no valid answer", record["error"])

    def test_purchase_details_are_treated_as_data(self):
        self.assertIn("never instructions", intake.SYSTEM_PROMPT)

    def test_accessories_count_as_gadgets(self):
        # The first eval run found an external hard drive declined as "not a gadget".
        self.assertIn("computer accessories such as", intake.SYSTEM_PROMPT)
        self.assertIn("storage drives", intake.SYSTEM_PROMPT)
        self.assertIn("An accessory takes the category of the device it serves.", intake.SYSTEM_PROMPT)


class Scoring(unittest.TestCase):
    """The mechanics that stay the same from one formula version to the next.
    The v2 rules (weights, cut-offs, lean rails) are tested in test_phase5_scoring.py."""

    def test_the_score_is_the_average_of_the_counted_ratings(self):
        # The Guardian's middle rating is cost_of_waiting, which has no weight: (21 + 2 + 2) / 5 = 5.0.
        final = {"The Analyst": reply_with(ANALYST, 7, 7, 7), "Budget Guardian": reply_with(BUDGET_GUARDIAN, 2, 9, 2)}
        result = scoring.score(final)
        self.assertEqual(result["score"], 5.0)
        self.assertEqual((result["verdict"], result["verdict_label"]), ("wait", "Wait 30 days"))
        self.assertEqual(result["inputs"]["The Analyst"], {"value_per_use": 7, "longevity": 7, "upgrade_gap": 7})
        self.assertEqual(result["inputs"]["Budget Guardian"]["cost_of_waiting"], 9)  # still recorded
        self.assertEqual(result["ratings_counted"], 5)
        self.assertEqual(result["formula_version"], 2)

    def test_thresholds(self):
        cases = {9.0: "buy", 5.5: "buy", 5.4: "wait", 4.5: "wait", 4.4: "skip", 1.0: "skip"}
        for value, verdict in cases.items():
            with self.subTest(score=value):
                self.assertEqual(scoring.verdict_for(value), verdict)

    def test_halves_round_up_like_people_expect(self):
        # 50 / 8 = 6.25 (the Guardian's cost_of_waiting is not counted, so 8 ratings count).
        # Python's round() gives 6.2 (it rounds halves to even); this gives 6.3.
        self.assertEqual(round(6.25, 1), 6.2)
        final = {
            "The Analyst": reply_with(ANALYST, 7, 7, 7),
            "Future You": reply_with(FUTURE_YOU, 6, 6, 5),
            "Budget Guardian": reply_with(BUDGET_GUARDIAN, 6, 1, 6),
        }
        self.assertEqual(scoring.score(final)["score"], 6.3)

    def test_same_ratings_same_result(self):
        final = {"The Analyst": reply_with(ANALYST, 3, 9, 4), "Future You": reply_with(FUTURE_YOU, 5, 6, 7)}
        self.assertEqual(scoring.score(final), scoring.score(final))

    def test_nothing_to_score_is_an_error(self):
        with self.assertRaises(ValueError):
            scoring.score({})


class FinalReplies(unittest.TestCase):
    def test_each_agent_keeps_its_last_good_reply(self):
        first = reply_with(ANALYST, 5, 5, 5)
        guardian_first = reply_with(BUDGET_GUARDIAN, 4, 4, 4)
        guardian_later = reply_with(BUDGET_GUARDIAN, 2, 2, 2)
        debate = Debate(PURCHASE, rounds=[
            Round(1, "opening", [
                Turn("The Analyst", "ok", first, {}),
                Turn("Future You", "failed", None, {}),
                Turn("Budget Guardian", "ok", guardian_first, {}),
            ]),
            Round(2, "rebuttal", [
                Turn("The Analyst", "failed", None, {}),
                Turn("Budget Guardian", "ok", guardian_later, {}),
            ]),
        ])
        final = final_replies(debate)
        self.assertEqual(list(final), ["The Analyst", "Budget Guardian"])  # Future You never answered
        self.assertIs(final["The Analyst"], first)  # failed round 2, keeps round 1
        self.assertIs(final["Budget Guardian"], guardian_later)


class Split(unittest.TestCase):
    def test_split_means_no_lean_held_by_three(self):
        cases = {
            ("buy", "buy", "wait", "wait"): True,
            ("buy", "buy", "wait", "skip"): True,
            ("wait", "wait", "wait", "buy"): False,
            ("skip", "skip", "skip", "skip"): False,
            ("buy", "buy", "wait"): True,  # three left: all three must agree
            ("wait", "wait", "wait"): False,
            ("buy", "wait"): True,  # two left: both must agree
            ("wait", "wait"): False,
        }
        for leans, split in cases.items():
            with self.subTest(leans=leans):
                self.assertEqual(is_split(list(leans)), split)


def judged_debate() -> tuple[Debate, dict]:
    take = ANALYST.take_schema.model_validate(take_for(ANALYST, lean="buy"))
    guardian = BUDGET_GUARDIAN.take_schema.model_validate(take_for(BUDGET_GUARDIAN))
    tool_call = {"ok": True, "duplicate": False, "result": {"summary": "Net cost $172.99, about $0.11 per use."}}
    debate = Debate(PURCHASE, rounds=[Round(1, "opening", [
        Turn("The Analyst", "ok", take, {"tool_calls": [tool_call]}),
        Turn("Budget Guardian", "ok", guardian, {"tool_calls": []}),
    ])])
    return debate, scoring.score(final_replies(debate))


class Judge(unittest.TestCase):
    def test_the_judge_has_no_way_to_give_a_verdict_or_a_score(self):
        for field in ("verdict", "score", "lean", "confidence"):
            self.assertNotIn(field, Ruling.model_fields)

    def test_the_judge_reads_the_debate_and_the_computed_result(self):
        debate, result = judged_debate()
        fake = FakeChat([judge_reply()])
        ruling, trace, fallback_used = judge.rule(debate, result, chat=fake)

        self.assertFalse(fallback_used)
        prompt = fake.calls[0]["messages"][1]["content"]
        self.assertIn("The Analyst leaned BUY", prompt)
        self.assertIn("Tool result: Net cost $172.99", prompt)
        self.assertIn(f"Score: {result['score']} out of 10", prompt)
        self.assertIn("Final leans: 1 BUY, 1 WAIT", prompt)
        self.assertIn(f"Verdict: {result['verdict_label']}", prompt)

    def test_a_number_that_is_not_in_the_debate_is_sent_back(self):
        debate, result = judged_debate()
        invented = judge_reply(ruling="At $150 net it is fair, but give it a month first.")
        grounded = judge_reply(ruling="At $172.99 net it is fair, but give it a month first.")
        fake = FakeChat([invented, grounded])
        ruling, trace, _ = judge.rule(debate, result, chat=fake)

        self.assertEqual([a["ok"] for a in trace["attempts"]], [False, True])
        self.assertIn("150 is not a number you were given", trace["attempts"][0]["error"])
        self.assertIn("$172.99", ruling.ruling)

    def test_rounding_a_number_from_the_debate_is_fine(self):
        debate, result = judged_debate()
        rounded = judge_reply(ruling="At about $173 net, or $0.1 a use, it is fair, but give it a month first.")
        _, trace, _ = judge.rule(debate, result, chat=FakeChat([rounded]))
        self.assertEqual([a["ok"] for a in trace["attempts"]], [True])

    def test_naming_a_member_with_no_final_answer_is_sent_back(self):
        debate, result = judged_debate()
        fake = FakeChat([judge_reply(most_persuasive="Future You"), judge_reply()])
        _, trace, _ = judge.rule(debate, result, chat=fake)
        self.assertIn("gave no final answer", trace["attempts"][0]["error"])

    def test_the_ruling_is_one_sentence_and_short(self):
        debate, result = judged_debate()
        two = judge_reply(ruling="Wait a month. Then decide.")
        long_one = judge_reply(ruling="Wait " + "and wait " * 30 + "then decide.")
        cut_off = judge_reply(ruling="The upgrade looks sharper, but waiting a month could help find a")  # from a live run
        for bad in (two, long_one, cut_off):
            with self.subTest(ruling=json.loads(bad)["ruling"][:30]):
                _, trace, _ = judge.rule(debate, result, chat=FakeChat([bad, judge_reply()]))
                self.assertFalse(trace["attempts"][0]["ok"])

    def test_a_failed_judge_falls_back_to_a_ruling_from_the_score(self):
        debate, result = judged_debate()
        ruling, trace, fallback_used = judge.rule(debate, result, chat=FakeChat(["bad"] * config.MAX_ATTEMPTS))

        self.assertTrue(fallback_used)
        self.assertIn(f"{result['score']} out of 10", ruling.ruling)
        self.assertEqual(len(trace["attempts"]), config.MAX_ATTEMPTS)

    def test_the_fallback_works_for_every_verdict(self):
        final = {"The Analyst": reply_with(ANALYST, 9, 3, 6), "Budget Guardian": reply_with(BUDGET_GUARDIAN, 2, 5, 5)}
        for verdict, value in (("buy", 7.0), ("wait", 5.0), ("skip", 2.0)):
            with self.subTest(verdict=verdict):
                result = {"score": value, "verdict": verdict}
                ruling = judge.fallback_ruling(result, final)
                self.assertLessEqual(len(ruling.ruling), 160)
                self.assertEqual(ruling.strongest_for.agent, "The Analyst")  # the single highest rating, 9
                self.assertEqual(ruling.strongest_against.agent, "Budget Guardian")  # the lowest, 2


class AgentNumbers(unittest.TestCase):
    """Every agent may only write numbers it was given: the purchase, its tool results, the debate."""

    def test_an_invented_number_in_a_take_is_sent_back(self):
        # The exact slip from the milestone 2 live run.
        invented = take_for(FUTURE_YOU, take="Six months later, I'm glad I upgraded. The extra $300 was worth it.")
        fake = FakeChat([json.dumps(invented), json.dumps(take_for(FUTURE_YOU))])
        _, trace, _ = open_turn(FUTURE_YOU, PURCHASE, chat=fake)

        self.assertEqual([a["ok"] for a in trace["attempts"]], [False, True])
        self.assertIn("300 is not a number you were given", trace["attempts"][0]["error"])

    def test_numbers_from_its_own_tool_results_are_fine(self):
        # cost_per_use on these arguments returns a $177.01 resale estimate and $0.11 per use.
        take = "You would pay about $0.11 per use after a resale estimate of $177.01. That is cheap for a commute."
        fake = FakeChat([tool_request("cost_per_use", COST_ARGS), json.dumps(take_for(ANALYST, take=take))])
        _, trace, _ = open_turn(ANALYST, PURCHASE, chat=fake)
        self.assertEqual([a["ok"] for a in trace["attempts"]], [True])

    def test_an_invented_number_in_a_reason_is_sent_back(self):
        invented = take_for(BUDGET_GUARDIAN)
        invented["ratings"]["price_for_the_problem"]["reason"] = "A used pair would be about $199 instead."
        fake = FakeChat([json.dumps(invented), json.dumps(take_for(BUDGET_GUARDIAN))])
        _, trace, _ = open_turn(BUDGET_GUARDIAN, PURCHASE, chat=fake)
        self.assertIn("ratings.price_for_the_problem.reason", trace["attempts"][0]["error"])

    def test_a_rebuttal_may_quote_numbers_from_the_digest_but_not_invent_them(self):
        _, _, conversation = open_turn(BUDGET_GUARDIAN, PURCHASE, chat=FakeChat([json.dumps(take_for(BUDGET_GUARDIAN))]))
        digest = render_round(opening_round(), exclude="Budget Guardian")  # has the Analyst's "$172.99"
        quoted = rebuttal_for(BUDGET_GUARDIAN, ["The Analyst"], response="The Analyst, $172.99 is still a lot for one problem.")
        invented = rebuttal_for(BUDGET_GUARDIAN, ["The Analyst"], response="The Analyst, $999 would be a lot for one problem.")

        _, trace, _ = rebuttal_turn(BUDGET_GUARDIAN, conversation, digest, ["The Analyst"],
                                    chat=FakeChat([json.dumps(quoted)]))
        self.assertEqual([a["ok"] for a in trace["attempts"]], [True])

        _, trace, _ = rebuttal_turn(BUDGET_GUARDIAN, conversation, digest, ["The Analyst"],
                                    chat=FakeChat([json.dumps(invented), json.dumps(quoted)]))
        self.assertIn("999 is not a number you were given", trace["attempts"][0]["error"])

    def test_the_hunter_has_no_example_cadence_to_copy(self):
        self.assertNotIn("refreshes about yearly", ALTERNATIVES_HUNTER.system_prompt())


class RunCouncil(unittest.TestCase):
    def test_end_to_end(self):
        events = []
        fake = FakeChat([intake_reply(), *opening_replies(), *rebuttal_replies(), judge_reply()])
        session = run_council(PURCHASE, chat=fake, on_event=events.append)

        self.assertEqual(session["kind"], "council")
        self.assertEqual([r["kind"] for r in session["rounds"]], ["opening", "rebuttal"])  # 4-0, no tiebreak
        self.assertEqual(session["intake"]["category"], "audio")
        self.assertEqual(session["scoring"]["score"], 6.0)  # every final rating in the script is 6
        self.assertEqual(session["scoring"]["verdict"], "wait")
        # 6.0 points to Buy, but all four members leaned Wait at the end, so a rail held it at Wait.
        self.assertEqual((session["scoring"]["score_verdict"], session["scoring"]["rail"]), ("buy", "buy_needs_a_buy_lean"))
        self.assertFalse(session["judge"]["fallback_used"])
        self.assertNotIn("verdict", session["judge"])  # the verdict lives in scoring, never with the Judge
        self.assertEqual(len(fake.calls), 1 + 6 + 4 + 1)
        json.dumps(session)  # plain data, ready to save

        kinds = [event["event"] for event in events]
        self.assertEqual(kinds[0], "intake_done")
        self.assertEqual(kinds[-2:], ["scored", "verdict"])

    def test_the_intake_category_reaches_every_agent(self):
        fake = FakeChat([intake_reply(category="audio"), *opening_replies(), *rebuttal_replies(), judge_reply()])
        run_council(PURCHASE, chat=fake)
        opening_calls = [call for call in fake.calls[1:7] if call["messages"][0]["role"] == "system"]
        for call in opening_calls:
            self.assertIn("Gadget category (use this exact word in tool calls): audio", call["messages"][1]["content"])

    def test_something_that_is_not_a_gadget_is_declined_politely(self):
        sofa = {"item": "Leather sofa", "price": 1200, "why": "My old couch sags.", "want_level": 6}
        fake = FakeChat([intake_reply(gadget=False)])
        session = run_council(sofa, chat=fake)

        self.assertEqual(session["kind"], "declined")
        self.assertEqual(session["rounds"], [])
        self.assertIsNone(session["scoring"])
        self.assertIn("only weighs in on tech gadgets", session["message"])
        self.assertIn('"Leather sofa" doesn\'t look like one.', session["message"])
        self.assertEqual(session["intake"]["note"], "A leather sofa is furniture.")  # kept in the record
        self.assertEqual(len(fake.calls), 1)

    def test_a_failed_intake_check_never_blocks_the_council(self):
        fake = FakeChat([*["bad"] * config.MAX_ATTEMPTS, *opening_replies(), *rebuttal_replies(), judge_reply()])
        session = run_council(PURCHASE, chat=fake)
        self.assertEqual(session["kind"], "council")
        self.assertFalse(session["intake"]["ok"])
        self.assertIsNone(session["intake"]["category"])

    def test_a_split_council_gets_a_tiebreak_up_to_the_cap(self):
        split = ["buy", "buy", "wait", "wait"]
        fake = FakeChat([intake_reply(), *opening_replies(), *rebuttals_with(split), *rebuttals_with(split),
                         judge_reply()])
        session = run_council(PURCHASE, chat=fake)

        self.assertEqual([r["kind"] for r in session["rounds"]], ["opening", "rebuttal", "tiebreak"])
        tiebreak_prompt = fake.calls[11]["messages"][-1]["content"]
        self.assertIn("The council is split (2 buy, 2 wait).", tiebreak_prompt)
        self.assertIn("This is the last round", tiebreak_prompt)

    def test_the_tiebreak_stops_once_the_council_agrees(self):
        fake = FakeChat([intake_reply(), *opening_replies(), *rebuttals_with(["buy", "buy", "wait", "wait"]),
                         *rebuttals_with(["wait", "buy", "wait", "wait"]), judge_reply()])
        session = run_council(PURCHASE, chat=fake, max_rounds=5)
        self.assertEqual(len(session["rounds"]), 3)  # round 3 settled it at 3-1, so no round 4

    def test_no_tiebreak_when_three_agree(self):
        fake = FakeChat([intake_reply(), *opening_replies(), *rebuttals_with(["buy", "wait", "wait", "wait"]),
                         judge_reply()])
        self.assertEqual(len(run_council(PURCHASE, chat=fake)["rounds"]), 2)

    def test_the_round_cap_is_a_hard_limit(self):
        fake = FakeChat([intake_reply(), *opening_replies(), *rebuttals_with(["buy", "buy", "wait", "wait"]),
                         judge_reply()])
        self.assertEqual(len(run_council(PURCHASE, chat=fake, max_rounds=2)["rounds"]), 2)

    def test_a_failed_judge_still_ends_with_a_verdict(self):
        fake = FakeChat([intake_reply(), *opening_replies(), *rebuttal_replies(), *["bad"] * config.MAX_ATTEMPTS])
        session = run_council(PURCHASE, chat=fake)
        self.assertTrue(session["judge"]["fallback_used"])
        self.assertIn("out of 10", session["judge"]["ruling"])
        self.assertEqual(session["scoring"]["verdict"], "wait")

    def test_fewer_than_two_answers_stops_with_a_clear_error(self):
        replies = opening_replies()
        bad = ["bad"] * config.MAX_ATTEMPTS
        # Only The Analyst answers: the other three never give valid JSON.
        script = [intake_reply(), *replies[:2], *bad, *bad, replies[4], *bad]
        with self.assertRaises(CouncilError):
            run_council(PURCHASE, chat=FakeChat(script))


if __name__ == "__main__":
    unittest.main()
