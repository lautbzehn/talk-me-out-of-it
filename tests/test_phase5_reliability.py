"""Phase 5 tests, reliability milestone (10.25.2026): text a gallery viewer would see broken, wasted
tool time, and the retries the 14B model kept needing. Each test names the live failure it guards
against. None of them call the real model.

Run with:  .venv/bin/python -m unittest -v
"""

import copy
import json
import unittest

from ollama import Tool
from pydantic import ValidationError

import config
from agents import judge
from agents.alternatives_hunter import ALTERNATIVES_HUNTER
from agents.analyst import ANALYST
from agents.council_agent import TOOL_OUTRO, open_turn, purchase_prompt
from agents.future_you import FUTURE_YOU
from agents.schemas import AgentTake, AnalystRatings, Point, Rating, Ruling, show_number, ungrounded_numbers
from evals import replay, report
from tests.helpers import FakeChat, tool_request
from tests.test_phase4 import PURCHASE, take_for
from tests.test_phase4_council import judge_reply, judged_debate
from tests.test_phase4_debate import rebuttal_for, validate
from tests.test_phase5_evals import COUNCIL_SESSION, opening_turn, scenario
from tools.cost_per_use import CostPerUseInput
from tools.registry import run_tool, tool_specs


def padded(ending: str, limit: int) -> str:
    """Text exactly `limit` characters long that ends with `ending`, like one Ollama closed at its limit."""
    start = "This purchase deserves a careful look. "
    return (start * (limit // len(start) + 1))[: limit - len(ending)] + ending


class CutOffText(unittest.TestCase):
    """Ollama closes a string at its max_length and the reply still looks normal. 4 texts in 39
    councils of the repeated 14B run were cut that way, 2 of them Judge summaries at 500 of 500."""

    def test_a_take_cut_at_its_limit_is_sent_back(self):
        take = padded("or the last year's model in the color you have now. Both options can", 500)
        with self.assertRaises(ValidationError) as caught:
            AgentTake[AnalystRatings].model_validate(take_for(ANALYST, take=take))
        self.assertIn("cut off mid-sentence", str(caught.exception))

    def test_a_text_that_ends_cleanly_at_its_limit_is_fine(self):
        for ending in (" That is the honest answer.", ' He said "check first."', " Is it worth it?"):
            with self.subTest(ending=ending):
                AgentTake[AnalystRatings].model_validate(take_for(ANALYST, take=padded(ending, 500)))

    def test_every_viewer_text_gets_the_check(self):
        reason = padded(" justify the cost, which seems unlikely given the low frequency of use", 200)  # live run
        with self.assertRaises(ValidationError):
            Rating(reason=reason, score=4)
        with self.assertRaises(ValidationError):
            Point(agent="The Analyst", point=padded(" but only if it gets used every", 200))
        summary = padded(" one BUY, resulting in a score of 5.6, leading to a verdict of Wait", 500)  # live run
        with self.assertRaises(ValidationError):
            Ruling.model_validate_json(judge_reply(summary=summary))
        with self.assertRaises(ValidationError):
            Ruling.model_validate_json(judge_reply(would_change_verdict=padded(" if they used it far", 200)))
        response = padded(" The Analyst is right that the numbers", 500)
        with self.assertRaises(ValidationError):
            validate(ANALYST, rebuttal_for(ANALYST, ["Future You"], response=response))

    def test_a_short_text_without_a_period_is_left_alone(self):
        Rating(reason="Fine for daily use, though not much better than what they have", score=6)

    def test_the_retry_asks_for_a_shorter_complete_version(self):
        cut = take_for(FUTURE_YOU, take=padded("and I wish I had", 500))
        fake = FakeChat([json.dumps(cut), json.dumps(take_for(FUTURE_YOU))])
        _, trace, _ = open_turn(FUTURE_YOU, PURCHASE, chat=fake)
        self.assertEqual([a["ok"] for a in trace["attempts"]], [False, True])
        self.assertIn("write a shorter version that is complete", fake.calls[-1]["messages"][-1]["content"])


class NotEnglish(unittest.TestCase):
    """Qwen switched to Chinese mid-sentence once in each 14B run ("better picture质量", "Both options can挠")."""

    def test_chinese_characters_are_sent_back_and_named(self):
        with self.assertRaises(ValidationError) as caught:
            Rating(reason="The new one has a better picture质量 than the old one.", score=6)
        self.assertIn("Chinese characters in it (质量)", str(caught.exception))

    def test_every_viewer_text_gets_the_check(self):
        with self.assertRaises(ValidationError):
            AgentTake[AnalystRatings].model_validate(take_for(ANALYST, take="It is fine. Both options can挠 work."))
        with self.assertRaises(ValidationError):
            Ruling.model_validate_json(judge_reply(ruling="The price is high for a small gain，so give it time."))
        with self.assertRaises(ValidationError):
            validate(ANALYST, rebuttal_for(ANALYST, ["Future You"], response="Future You, 质量 matters more here."))

    def test_curly_quotes_and_symbols_are_fine(self):
        Rating(reason="It’s “good enough” for now, and that’s fine… mostly.", score=6)


class SavedReplies(unittest.TestCase):
    def test_replay_does_not_judge_old_texts_by_new_rules(self):
        # The saved 14B runs hold the Chinese take and cut-off texts. Step 4 replays them, so they must rebuild.
        session = copy.deepcopy(COUNCIL_SESSION)
        opening_turn(session, "The Analyst")["take_or_rebuttal"]["take"] = padded("Both options can挠", 500)
        debate = replay.rebuild_debate(session)
        self.assertTrue(debate.rounds[0].turns[0].reply.take.endswith("挠"))


class JudgeMainReason(unittest.TestCase):
    """Under the key `ruling` the 14B opened with the verdict in 37 of 52 councils."""

    def test_the_model_sees_main_reason_and_code_keeps_ruling(self):
        shown = Ruling.model_json_schema()["properties"]
        self.assertIn("main_reason", shown)
        self.assertNotIn("ruling", shown)
        self.assertIn("6. main_reason:", judge.SYSTEM_PROMPT)

        data = json.loads(judge_reply())
        data["main_reason"] = data.pop("ruling")
        ruling = Ruling.model_validate_json(json.dumps(data))
        self.assertIn("ruling", ruling.model_dump())  # saved sessions keep their key
        self.assertEqual(ruling.ruling, data["main_reason"])

    def test_a_reason_that_starts_with_the_verdict_is_sent_back(self):
        live = [
            "Wait 30 days to explore cheaper alternatives or better deals.",
            "Skip due to high price and limited use case.",
            "Skip: The high cost and depreciation rate outweigh the benefits for occasional use.",
            "Skipping the purchase due to unclear need and high cost.",
            "Buy: the daily commute makes this an easy call.",
        ]
        debate, result = judged_debate()
        for text in live:
            with self.subTest(text=text):
                fake = FakeChat([judge_reply(ruling=text), judge_reply()])
                _, trace, _ = judge.rule(debate, result, chat=fake)
                self.assertEqual([a["ok"] for a in trace["attempts"]], [False, True])
                self.assertIn("verdict card already shows it", trace["attempts"][0]["error"])

    def test_a_verdict_word_later_in_the_sentence_is_fine(self):
        Ruling.model_validate_json(judge_reply(ruling="The upfront cost is high and there are savings from waiting."))

    def test_the_fallback_never_starts_with_the_verdict(self):
        for verdict in ("buy", "wait", "skip"):
            with self.subTest(verdict=verdict):
                text = judge.FALLBACK[verdict][0].format(score=5.0)
                self.assertFalse(text.lower().startswith(verdict))
        for rail, (text, _) in judge.RAIL_FALLBACK.items():
            with self.subTest(rail=rail):
                self.assertFalse(text.format(score=5.0).lower().startswith(("buy", "wait", "skip")))


class WantLevel(unittest.TestCase):
    """Future You copied "7/10" from the purchase prompt into a reason in 4 turns, twice the same text again."""

    def test_the_purchase_never_shows_a_number_out_of_10(self):
        prompt = purchase_prompt(PURCHASE)
        self.assertNotIn("/10", prompt)
        self.assertIn("their want level, 7 on a scale of 1 to 10", prompt)

    def test_the_retry_quotes_what_it_found_and_what_to_write(self):
        with self.assertRaises(ValidationError) as caught:
            Rating(reason="The commute is real, but the desire wasn't as intense as a 7/10 would suggest.", score=5)
        message = str(caught.exception)
        self.assertIn('("7/10")', message)
        self.assertIn('"their want level of 7"', message)

    def test_the_suggested_wording_passes(self):
        Rating(reason="The commute is real, but not as pressing as their want level of 7 suggests.", score=5)


class Grounding(unittest.TestCase):
    def test_durations_are_allowed(self):
        # The 14B Hunter lost a whole turn to "12 months".
        for text in ("Prices often drop within 12 months.", "A 24-month plan.", "It has 365 days to prove itself.",
                     "Over 18 Months of use.", "About 52 weeks a year."):
            with self.subTest(text=text):
                self.assertEqual(ungrounded_numbers(text, {350.0}), [])

    def test_money_and_percentages_are_still_checked(self):
        self.assertEqual(ungrounded_numbers("It might cost $12 a month.", {350.0}), ["12"])
        self.assertEqual(ungrounded_numbers("You may lose 66% of the price.", {350.0}), ["66"])
        self.assertEqual(ungrounded_numbers("Expect a new one in 2026.", {350.0}), ["2026"])

    def test_the_retry_names_the_closest_number_given(self):
        # Live run: "about $335" for the tool's $335.83, the same number again on every retry.
        rejected = take_for(ANALYST, take="The resale value after 5 years is only about $335. That is a big loss.")
        fake = FakeChat([tool_request("cost_per_use", {"price": 700, "uses_per_week": 2, "years": 5,
                                                      "category": "console"}),
                         json.dumps(rejected), json.dumps(take_for(ANALYST))])
        purchase = PURCHASE.model_copy(update={"price": 700.0})
        _, trace, _ = open_turn(ANALYST, purchase, chat=fake)
        error = trace["attempts"][0]["error"]
        self.assertIn("335 is not a number you were given", error)
        self.assertIn("335.83 instead of 335", error)

    def test_no_hint_when_nothing_is_close(self):
        # Live run: "lose 66%" was 100 minus the tool's 34; the nearest numbers given (80, 48) mean something else.
        take = "You may lose 66% of what you paid by the time you sell it. That is a lot to give up."
        fake = FakeChat([json.dumps(take_for(ANALYST, take=take)),
                         json.dumps(take_for(ANALYST))])
        _, trace, _ = open_turn(ANALYST, PURCHASE, chat=fake, use_tools=False)
        error = trace["attempts"][0]["error"]
        self.assertIn("66 is not a number you were given", error)
        self.assertIn("or leave the number out", error)
        self.assertNotIn("instead of", error)

    def test_numbers_are_shown_the_way_they_first_appeared(self):
        self.assertEqual([show_number(v) for v in (335.83, 1560.0, 0.5, 100.0)], ["335.83", "1,560", "0.5", "100"])


class ToolSpecs(unittest.TestCase):
    """The Ollama client keeps only type, description, enum and items of each argument. An optional
    `category` lost its type and its list, and the 14B passed `object: "phone"` in 9 of 39 councils."""

    def test_every_argument_reaches_the_model_with_a_type(self):
        for spec in tool_specs():
            sent = Tool.model_validate(spec).model_dump(exclude_none=True)["function"]
            for name, prop in sent["parameters"]["properties"].items():
                with self.subTest(tool=sent["name"], argument=name):
                    self.assertIn("type", prop)

    def test_the_optional_category_keeps_its_list(self):
        sent = Tool.model_validate(tool_specs(["cost_per_use"])[0]).model_dump(exclude_none=True)
        category = sent["function"]["parameters"]["properties"]["category"]
        self.assertEqual((category["type"], len(category["enum"])), ("string", 9))
        self.assertNotIn("category", sent["function"]["parameters"]["required"])

    def test_category_is_still_optional(self):
        self.assertTrue(run_tool("cost_per_use", {"price": 350, "uses_per_week": 10, "years": 3})["ok"])
        self.assertTrue(run_tool("cost_per_use", {"price": 350, "uses_per_week": 10, "years": 3, "category": None})["ok"])

    def test_a_made_up_argument_gets_the_real_inputs_back(self):
        record = run_tool("cost_per_use", {"object": "phone", "price": 1200, "uses_per_week": 7, "years": 2})
        self.assertFalse(record["ok"])
        self.assertIn("cost_per_use has no input called object", record["error"])
        self.assertIn("its inputs are: price, uses_per_week, years, category", record["error"])

    def test_the_analyst_guide_names_every_input(self):
        for name in CostPerUseInput.model_fields:
            self.assertIn(name, ANALYST.tool_guide)


class ToolStepLength(unittest.TestCase):
    """Without being told, the 14B wrote its whole JSON reply after its tool calls, before any results:
    about 120 tokens and 10 seconds per tool step, thrown away by Ollama without a word."""

    def test_the_tool_step_is_told_to_send_only_the_calls(self):
        self.assertIn("send only the tool calls in that message", TOOL_OUTRO)
        for agent in (ANALYST, ALTERNATIVES_HUNTER):
            self.assertIn("send only the tool calls", agent.system_prompt())

    def test_the_cap_leaves_room_for_two_calls(self):
        # A step with two calls is about 80 tokens; every reply that hit the old cap of 400 was a loop.
        self.assertGreaterEqual(config.MAX_TOOL_TURN_TOKENS, 160)
        self.assertLessEqual(config.MAX_TOOL_TURN_TOKENS, 250)
        fake = FakeChat([tool_request("cost_per_use", {"price": 350, "uses_per_week": 10, "years": 3}),
                         json.dumps(take_for(ANALYST))])
        open_turn(ANALYST, PURCHASE, chat=fake)
        self.assertEqual(fake.calls[0]["options"]["num_predict"], config.MAX_TOOL_TURN_TOKENS)


class ReportChecks(unittest.TestCase):
    def test_a_member_naming_its_own_tool_or_rubric_item_is_not_a_voice_slip(self):
        session = copy.deepcopy(COUNCIL_SESSION)
        take = opening_turn(session, "The Analyst")["take_or_rebuttal"]
        take["take"] = "My cost_per_use is low. My value_per_use rating stands, and so does my longevity score."
        self.assertFalse([flag for flag in report.voice_flags(session) if "The Analyst" in flag["where"]])
        take["take"] = "This helps my daily commute a lot. It is worth it."
        self.assertTrue([flag for flag in report.voice_flags(session) if "The Analyst" in flag["where"]])

    def test_cut_off_and_chinese_texts_are_counted(self):
        session = copy.deepcopy(COUNCIL_SESSION)
        opening_turn(session, "The Analyst")["take_or_rebuttal"]["take"] = padded("Both options can挠", 500)
        opening_turn(session, "Budget Guardian")["take_or_rebuttal"]["take"] = padded(" That is fine.", 500)
        row = report.row_for(scenario(), session)
        self.assertEqual([item["cut_off"] for item in row["at_limit"]], [True, False])
        self.assertEqual(len(row["not_english"]), 1)
        summary = report.summarize([row])
        self.assertEqual((summary["texts_at_limit"], summary["texts_cut_off"], summary["texts_not_english"]), (2, 1, 1))


if __name__ == "__main__":
    unittest.main()
