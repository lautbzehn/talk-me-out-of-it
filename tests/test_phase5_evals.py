"""Phase 5 tests, step 2: the eval report and the eval runner. None of them call the real model:
sessions come from run_council with the fake model, then get edited to set up each case.

Run with:  .venv/bin/python -m unittest -v
"""

import copy
import json
import tempfile
import unittest
from pathlib import Path

import config
import scoring
from council import run_council
from evals import report
from evals.run_evals import pick, rebuild, run_evals, session_file, use_model
from evals.scenarios import Scenario, load_scenarios
from tests.helpers import FakeChat
from tests.test_phase4 import PURCHASE
from tests.test_phase4_council import intake_reply, judge_reply
from tests.test_phase4_debate import opening_replies, rebuttal_replies

SOFA = {"item": "Leather sofa", "price": 1200, "why": "My old couch sags.", "want_level": 6}


def council_script() -> list:
    """Scripted replies for one full council: every final lean is wait, every final rating 6."""
    return [intake_reply(), *opening_replies(), *rebuttal_replies(), judge_reply()]


COUNCIL_SESSION = run_council(PURCHASE, chat=FakeChat(council_script()))
DECLINED_SESSION = run_council(SOFA, chat=FakeChat([intake_reply(gadget=False)]))


def council(**scoring) -> dict:
    """A fresh copy of the scripted council session, with scoring fields replaced."""
    session = copy.deepcopy(COUNCIL_SESSION)
    session["scoring"].update(scoring)
    return session


def scenario(expected="wait", category="audio", id="headphones") -> Scenario:
    return Scenario(id=id, expected=expected, category=category, tags=[], why_expected="A test scenario.",
                    purchase=PURCHASE)


def opening_turn(session: dict, agent: str) -> dict:
    return next(turn for turn in session["rounds"][0]["turns"] if turn["agent"] == agent)


class OneRow(unittest.TestCase):
    def test_a_council_that_agrees(self):
        row = report.row_for(scenario("wait"), COUNCIL_SESSION)
        self.assertEqual((row["got"], row["match"], row["distance"]), ("wait", True, 0))
        self.assertEqual(row["score"], 6.0)
        self.assertEqual((row["majority"], row["tally"]), ("wait", "4 wait"))
        self.assertFalse(row["against_majority"] or row["against_every_lean"])
        self.assertEqual((row["rounds"], row["turns"], row["tiebreak"]), (2, 8, False))
        self.assertEqual((row["rejected_attempts"], row["failed_turns"], row["judge_fallback"]), (0, 0, False))
        self.assertTrue(row["category_match"])

    def test_misses_are_near_or_far(self):
        self.assertEqual(report.row_for(scenario("buy"), council(verdict="wait"))["distance"], 1)
        self.assertEqual(report.row_for(scenario("buy"), council(verdict="skip"))["distance"], 2)

    def test_a_verdict_against_the_council_is_flagged(self):
        row = report.row_for(scenario("buy"), council(verdict="buy"))  # every member leaned wait
        self.assertTrue(row["against_majority"])
        self.assertTrue(row["against_every_lean"])

    def test_the_majority_needs_more_than_half(self):
        self.assertIsNone(report.majority(["buy", "buy", "wait", "wait"]))
        self.assertEqual(report.majority(["buy", "wait", "wait", "wait"]), "wait")
        self.assertEqual(report.majority(["buy", "wait", "wait"]), "wait")
        self.assertIsNone(report.majority([]))

    def test_the_opening_leans_are_compared_with_the_final_ones(self):
        row = report.row_for(scenario(), COUNCIL_SESSION)
        self.assertEqual(row["opening_majority"], "wait")  # 3 wait, 1 buy in the opening round
        self.assertFalse(row["majority_flipped"])
        self.assertEqual(row["changed_minds"], 1)  # the Analyst went from buy to wait

    def test_a_declined_purchase(self):
        row = report.row_for(scenario("declined", category=None), DECLINED_SESSION)
        self.assertEqual((row["got"], row["match"], row["distance"], row["score"]), ("declined", True, None, None))
        wrongly = report.row_for(scenario("buy"), DECLINED_SESSION)
        self.assertFalse(wrongly["match"])
        self.assertIsNone(wrongly["category_match"])  # no category to check once it was declined

    def test_a_wrong_category_is_caught(self):
        self.assertFalse(report.row_for(scenario(category="console"), COUNCIL_SESSION)["category_match"])
        self.assertIsNone(report.row_for(scenario(category=None), COUNCIL_SESSION)["category_match"])

    def test_a_stopped_council(self):
        session = {"kind": "error", "error": "Only 1 agent(s) answered round 1.", "rounds": [],
                   "timing": {"total_seconds": 40.0}}
        row = report.row_for(scenario(), session)
        self.assertEqual((row["got"], row["match"], row["error"]), ("error", False, "Only 1 agent(s) answered round 1."))


class Retries(unittest.TestCase):
    def test_rejected_attempts_are_counted_and_grouped_by_field(self):
        script = council_script()
        script.insert(3, "not json")  # Future You's first opening answer is broken
        session = run_council(PURCHASE, chat=FakeChat(script))
        row = report.row_for(scenario(), session)
        self.assertEqual(row["rejected_attempts"], 1)
        self.assertEqual(row["rejections"], {"the reply as a whole": 1})

    def test_rejection_fields(self):
        self.assertEqual(report.rejection_field("take: Value error, the take has 1 sentence(s)"), "take")
        self.assertEqual(report.rejection_field("ratings.longevity.score: Input should be <= 10"), "ratings.longevity.score")
        self.assertEqual(report.rejection_field("input: Invalid JSON: EOF"), "the reply as a whole")

    def test_token_cap_hits_are_counted(self):
        session = copy.deepcopy(COUNCIL_SESSION)
        opening_turn(session, "Budget Guardian")["trace"]["attempts"][0]["cut_off"] = True
        self.assertEqual(report.row_for(scenario(), session)["token_cap_hits"], 1)


class TextChecks(unittest.TestCase):
    def test_limits_come_from_the_schemas(self):
        self.assertEqual(report.LIMITS["take"], 500)
        self.assertEqual(report.LIMITS["ruling"], 160)

    def test_a_text_at_its_limit_is_flagged(self):
        for length, flagged in ((500, True), (498, True), (497, False)):
            with self.subTest(length=length):
                session = copy.deepcopy(COUNCIL_SESSION)
                opening_turn(session, "The Analyst")["take_or_rebuttal"]["take"] = "x" * length
                found = report.at_limit(session)
                self.assertEqual(bool(found), flagged)
                if flagged:
                    self.assertEqual((found[0]["field"], found[0]["limit"]), ("take", 500))

    def test_a_template_ruling_is_not_checked(self):
        session = copy.deepcopy(COUNCIL_SESSION)
        self.assertTrue(any(where == "Judge" for where, _, _ in report.texts(session)))
        session["judge"]["fallback_used"] = True
        self.assertFalse(any(where.startswith("Judge") for where, _, _ in report.texts(session)))

    def test_future_you_must_open_six_months_later_and_never_say_you(self):
        session = copy.deepcopy(COUNCIL_SESSION)
        take = opening_turn(session, "Future You")["take_or_rebuttal"]
        take["take"] = "This is fair for what you described. Still worth a second look."
        issues = [flag["issue"] for flag in report.voice_flags(session)]
        self.assertEqual(len(issues), 2)
        take["take"] = "Six months later, I still use them every day. I am glad I bought them."
        self.assertEqual(report.voice_flags(session), [])

    def test_other_members_speaking_as_the_user_are_flagged(self):
        session = copy.deepcopy(COUNCIL_SESSION)
        take = opening_turn(session, "Budget Guardian")["take_or_rebuttal"]
        take["take"] = "This would be a game-changer for my daily commute. I use them every day."
        flags = [flag for flag in report.voice_flags(session) if "Budget Guardian" in flag["where"]]
        self.assertEqual(len(flags), 1)
        self.assertIn("my daily", flags[0]["issue"])
        self.assertIn("I use", flags[0]["issue"])

    def test_a_member_talking_about_its_own_view_is_fine(self):
        session = copy.deepcopy(COUNCIL_SESSION)
        take = opening_turn(session, "Budget Guardian")["take_or_rebuttal"]
        take["take"] = "My view is that the price is high. My assumption is that it gets used daily."
        self.assertFalse([flag for flag in report.voice_flags(session) if "Budget Guardian" in flag["where"]])


class Summary(unittest.TestCase):
    def setUp(self):
        self.rows = [
            report.row_for(scenario("wait", id="right"), council(verdict="wait")),
            report.row_for(scenario("buy", id="far"), council(verdict="skip")),
            report.row_for(scenario("skip", id="near"), council(verdict="wait")),
            report.row_for(scenario("declined", category=None, id="sofa"), DECLINED_SESSION),
            report.row_for(scenario("buy", id="wrongly-declined"), DECLINED_SESSION),
        ]
        self.summary = report.summarize(self.rows)

    def test_headline_numbers(self):
        s = self.summary
        self.assertEqual((s["runs"], s["matched"]), (5, 2))
        self.assertEqual((s["verdicts_matched"], s["verdicts_expected"]), (1, 4))
        self.assertEqual((s["near_misses"], s["far_misses"]), (1, 1))
        self.assertEqual((s["declines_right"], s["declines_expected"], s["wrongly_declined"]), (1, 1, 1))
        self.assertEqual((s["councils"], s["against_majority"], s["against_every_lean"]), (3, 1, 1))

    def test_the_confusion_table(self):
        confusion = self.summary["confusion"]
        self.assertEqual(confusion["buy"]["skip"], 1)
        self.assertEqual(confusion["buy"]["declined"], 1)
        self.assertEqual(confusion["skip"]["wait"], 1)
        self.assertEqual(confusion["declined"]["declined"], 1)

    def test_retries_per_turn(self):
        self.assertEqual(self.summary["turns"], 24)
        self.assertEqual(self.summary["rejected_per_turn"], 0.0)

    def test_repeats_show_how_stable_a_scenario_is(self):
        rows = [report.row_for(scenario(), council(verdict="wait"), repeat) for repeat in (1, 2)]
        rows.append(report.row_for(scenario(id="other"), council(verdict="wait"), 1))
        rows.append(report.row_for(scenario(id="other"), council(verdict="buy"), 2))
        s = report.summarize(rows)
        self.assertEqual((s["repeated"], s["stable"]), (2, 1))

    def test_the_report_reads_well(self):
        text = report.render({"run_id": "test", "model": "fake", "formula_version": 1, "scenarios_version": "v1.0",
                              "started_at": "now", "finished_at": "later"}, self.rows, self.summary)
        self.assertIn("**Agreement with the expected outcome: 2 of 5 (40%)**", text)
        self.assertIn("1 near misses (one step off), 1 far misses", text)
        self.assertIn("| far | Buy | Skip (**no**) |", text)
        self.assertIn("| Buy |  |  | 1 | 1 |  |", text)  # the confusion row for Buy
        self.assertNotIn("—", text)

    def test_minutes(self):
        self.assertEqual(report.minutes(215), "3m 35s")
        self.assertEqual(report.minutes(45.2), "45s")


class Runner(unittest.TestCase):
    def test_a_run_saves_every_session_and_a_report_that_can_be_rebuilt(self):
        scenarios = [scenario("wait"), scenario("declined", category=None, id="sofa")]
        scenarios[1] = scenarios[1].model_copy(update={"purchase": scenarios[1].purchase.model_validate(SOFA)})
        chat = FakeChat([*council_script(), intake_reply(gadget=False)])
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "test-run"
            text = run_evals(scenarios, folder, "v1.0", chat=chat, say=lambda line: None)

            self.assertIn("2 of 2 (100%)", text)
            self.assertTrue(session_file(folder, "headphones", 1).exists())
            self.assertEqual(json.loads(session_file(folder, "sofa", 1).read_text())["kind"], "declined")
            info = json.loads((folder / "run.json").read_text())
            self.assertEqual((info["model"], info["formula_version"]), (config.MODEL, scoring.FORMULA_VERSION))
            self.assertEqual(info["request_timeout_seconds"], config.REQUEST_TIMEOUT_SECONDS)
            self.assertIsNotNone(info["finished_at"])
            saved = json.loads((folder / "report.json").read_text())
            self.assertEqual(saved["summary"]["matched"], 2)
            self.assertNotIn("scenarios", saved["run"])  # kept in run.json only

            self.assertEqual(rebuild(folder), text)  # same report from the saved sessions, no model

    def test_a_council_that_stops_is_recorded_and_the_run_goes_on(self):
        replies = opening_replies()
        bad = ["bad"] * config.MAX_ATTEMPTS
        only_the_analyst = [intake_reply(), *replies[:2], *bad, *bad, replies[4], *bad]
        scenarios = [scenario("wait"), scenario("declined", category=None, id="sofa")]
        chat = FakeChat([*only_the_analyst, intake_reply(gadget=False)])
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "test-run"
            text = run_evals(scenarios, folder, "v1.0", chat=chat, say=lambda line: None)
            stopped = json.loads(session_file(folder, "headphones", 1).read_text())
        self.assertEqual(stopped["kind"], "error")
        self.assertIn("Councils that stopped with an error: 1", text)
        self.assertIn("1 of 2 (50%)", text)

    def test_another_model_must_be_downloaded_first(self):
        self.addCleanup(setattr, config, "MODEL", config.MODEL)  # put the real model back afterwards
        with self.assertRaisesRegex(SystemExit, "ollama pull qwen2.5:7b"):
            use_model("qwen2.5:7b", ["qwen2.5:14b"])
        use_model("qwen2.5:7b", ["qwen2.5:14b", "qwen2.5:7b"])
        self.assertEqual(config.MODEL, "qwen2.5:7b")

    def test_only_picks_scenarios_by_id_and_rejects_unknown_ones(self):
        scenario_set = load_scenarios()
        picked = pick(scenario_set, "road-bike, commute-headphones")
        self.assertEqual([s.id for s in picked], ["commute-headphones", "road-bike"])  # file order
        self.assertEqual(len(pick(scenario_set, None)), len(scenario_set.scenarios))
        with self.assertRaises(SystemExit):
            pick(scenario_set, "no-such-scenario")


if __name__ == "__main__":
    unittest.main()
