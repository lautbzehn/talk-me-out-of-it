"""Phase 3 tests: the calculators, the tool shelf, the tool loop, and the Analyst's two phases.
None of them call the real model.

Run with:  .venv/bin/python -m unittest -v
"""

import json
import unittest

from pydantic import ValidationError

from agents.analyst import ANALYST
from agents.council_agent import open_turn
from agents.schemas import Purchase
from agents.tool_loop import run_tool_phase
import config
from agents.base import StructuredOutputError, call_structured_from_messages
from tests.helpers import FakeChat, cut_off, tool_request
from tests.test_phase2 import valid_take
from tools.cost_per_use import CostPerUseInput, cost_per_use
from tools.registry import run_tool, tool_specs
from tools.resale import DEPRECIATION, ResaleInput, estimate_resale

GOOD_COST_ARGS = {"price": 600, "uses_per_week": 5, "years": 2}


class CostPerUse(unittest.TestCase):
    def test_known_numbers(self):
        # 5 uses a week x 52 weeks x 2 years = 520 uses. $600 / 520 = $1.15 per use.
        result = cost_per_use(CostPerUseInput(**GOOD_COST_ARGS))
        self.assertEqual(result["total_uses"], 520)
        self.assertEqual(result["cost_per_use"], 1.15)
        self.assertEqual(result["cost_per_month"], 25.0)

    def test_a_category_subtracts_the_estimated_resale_value(self):
        # Audio, 2 years: 600 x 0.70 x 0.85 = 357.00 back, so the net cost is 243.00.
        result = cost_per_use(CostPerUseInput(**GOOD_COST_ARGS, category="audio"))
        self.assertEqual(result["resale_value_used"], 357.0)
        self.assertEqual(result["net_cost"], 243.0)
        self.assertEqual(result["cost_per_use"], 0.47)
        self.assertIn("unverified", result["summary"])

    def test_no_category_means_no_resale_credit(self):
        result = cost_per_use(CostPerUseInput(**GOOD_COST_ARGS))
        self.assertEqual(result["resale_value_used"], 0)
        self.assertEqual(result["net_cost"], 600.0)

    def test_the_model_cannot_type_its_own_resale_amount(self):
        with self.assertRaises(ValidationError):
            CostPerUseInput(**GOOD_COST_ARGS, resale_value=200)
        record = run_tool("cost_per_use", {**GOOD_COST_ARGS, "resale_value": 200})
        self.assertFalse(record["ok"])
        self.assertIn("resale_value", record["error"])

    def test_same_input_same_answer(self):
        first = cost_per_use(CostPerUseInput(**GOOD_COST_ARGS))
        second = cost_per_use(CostPerUseInput(**GOOD_COST_ARGS))
        self.assertEqual(first, second)

    def test_rejects_nonsense_inputs(self):
        bad_inputs = [
            {**GOOD_COST_ARGS, "uses_per_week": 0},
            {**GOOD_COST_ARGS, "years": -1},
            {**GOOD_COST_ARGS, "price": 0},
            {**GOOD_COST_ARGS, "category": "yacht"},
        ]
        for bad in bad_inputs:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    CostPerUseInput(**bad)


class Resale(unittest.TestCase):
    def test_one_year_loses_the_first_year_share(self):
        for category, (first_year, _) in DEPRECIATION.items():
            with self.subTest(category=category):
                result = estimate_resale(ResaleInput(price=1000, category=category, years_owned=1))
                self.assertAlmostEqual(result["estimated_resale_value"], 1000 * (1 - first_year), places=2)

    def test_known_number(self):
        # Audio: 30% lost in year one, 15% of what's left each later year.
        # 350 x 0.70 x 0.85 x 0.85 = 177.01
        result = estimate_resale(ResaleInput(price=350, category="audio", years_owned=3))
        self.assertEqual(result["estimated_resale_value"], 177.01)
        self.assertEqual(result["percent_retained"], 51)

    def test_value_only_goes_down_and_never_below_zero(self):
        for category in DEPRECIATION:
            values = [
                estimate_resale(ResaleInput(price=500, category=category, years_owned=years))["estimated_resale_value"]
                for years in (0.5, 1, 2, 5, 15)
            ]
            self.assertEqual(values, sorted(values, reverse=True), category)
            self.assertGreater(values[-1], 0)

    def test_every_result_is_labeled_unverified(self):
        result = estimate_resale(ResaleInput(price=500, category="phone", years_owned=2))
        self.assertIn("unverified", result["label"])
        self.assertIn("not a market price", result["summary"])

    def test_unknown_category_is_rejected(self):
        with self.assertRaises(ValidationError):
            ResaleInput(price=500, category="yacht", years_owned=2)


class Registry(unittest.TestCase):
    def test_specs_have_the_shape_ollama_expects(self):
        specs = tool_specs()
        self.assertEqual([s["function"]["name"] for s in specs], ["cost_per_use", "estimate_resale"])
        for spec in specs:
            self.assertEqual(spec["type"], "function")
            self.assertIn("properties", spec["function"]["parameters"])

    def test_good_call_returns_a_result(self):
        record = run_tool("cost_per_use", GOOD_COST_ARGS)
        self.assertTrue(record["ok"])
        self.assertEqual(record["result"]["cost_per_use"], 1.15)

    def test_numbers_sent_as_text_still_work(self):
        record = run_tool("cost_per_use", {"price": "600", "uses_per_week": "5", "years": "2"})
        self.assertTrue(record["ok"])

    def test_arguments_sent_as_a_json_string_still_work(self):
        record = run_tool("cost_per_use", json.dumps(GOOD_COST_ARGS))
        self.assertTrue(record["ok"])

    def test_bad_arguments_return_an_error_instead_of_crashing(self):
        record = run_tool("cost_per_use", {"price": 600, "uses_per_week": 0, "years": 2})
        self.assertFalse(record["ok"])
        self.assertIn("uses_per_week", record["error"])

    def test_missing_arguments_name_the_missing_field(self):
        record = run_tool("cost_per_use", {"price": 600})
        self.assertFalse(record["ok"])
        self.assertIn("years", record["error"])

    def test_unknown_tool_lists_the_real_ones(self):
        record = run_tool("buy_it_now", {})
        self.assertFalse(record["ok"])
        self.assertIn("cost_per_use", record["error"])

    def test_garbage_arguments_do_not_crash(self):
        for garbage in ["not json", 42, None, ["a"]]:
            with self.subTest(garbage=garbage):
                self.assertFalse(run_tool("cost_per_use", garbage)["ok"])


def start_messages():
    return [{"role": "system", "content": "system"}, {"role": "user", "content": "user"}]


class ToolLoop(unittest.TestCase):
    def test_runs_the_tool_and_hands_the_result_back(self):
        fake = FakeChat([tool_request("cost_per_use", GOOD_COST_ARGS), "Done calculating."])
        messages = start_messages()
        trace = run_tool_phase(messages, chat=fake)

        self.assertEqual(trace["stopped"], "model_finished")
        self.assertEqual(len(trace["tool_calls"]), 1)
        self.assertEqual(len(fake.calls), 2)
        # The second model call must have seen the tool's result.
        tool_message = fake.calls[1]["messages"][-1]
        self.assertEqual(tool_message["role"], "tool")
        self.assertEqual(tool_message["tool_name"], "cost_per_use")
        self.assertIn("1.15", tool_message["content"])
        # The tool menu is sent on every call.
        self.assertEqual(len(fake.calls[0]["tools"]), 2)

    def test_bad_arguments_go_back_to_the_model_which_can_fix_them(self):
        bad = {"price": 600, "uses_per_week": 0, "years": 2}
        fake = FakeChat([tool_request("cost_per_use", bad), tool_request("cost_per_use", GOOD_COST_ARGS), "Done."])
        trace = run_tool_phase(start_messages(), chat=fake, required=("cost_per_use",))

        self.assertEqual([c["ok"] for c in trace["tool_calls"]], [False, True])
        error_text = fake.calls[1]["messages"][-1]["content"]
        self.assertIn("uses_per_week", error_text)
        self.assertEqual(trace["missing_required"], [])

    def test_required_tool_is_enforced_by_a_reminder(self):
        fake = FakeChat(["I'll just answer.", tool_request("cost_per_use", GOOD_COST_ARGS), "Done."])
        trace = run_tool_phase(start_messages(), chat=fake, required=("cost_per_use",))

        self.assertEqual(trace["nudges"], 1)
        self.assertIn("cost_per_use", fake.calls[1]["messages"][-1]["content"])
        self.assertEqual(trace["missing_required"], [])
        self.assertEqual(len(trace["tool_calls"]), 1)

    def test_gives_up_reminding_and_reports_the_missing_tool(self):
        fake = FakeChat(["No."] * 3)
        trace = run_tool_phase(start_messages(), chat=fake, required=("cost_per_use",), max_nudges=2)

        self.assertEqual(trace["nudges"], 2)
        self.assertEqual(trace["missing_required"], ["cost_per_use"])
        self.assertEqual(trace["stopped"], "model_finished")

    def test_a_failed_call_does_not_count_as_using_the_required_tool(self):
        bad = {"price": 600}
        fake = FakeChat([tool_request("cost_per_use", bad), "Done.", "Done again."])
        trace = run_tool_phase(start_messages(), chat=fake, required=("cost_per_use",), max_nudges=1)
        self.assertEqual(trace["missing_required"], ["cost_per_use"])

    def test_step_limit_stops_a_model_that_never_stops(self):
        fake = FakeChat([tool_request("cost_per_use", {**GOOD_COST_ARGS, "years": n + 1}) for n in range(10)])
        trace = run_tool_phase(start_messages(), chat=fake, max_steps=3)

        self.assertEqual(trace["stopped"], "max_steps")
        self.assertEqual(len(fake.calls), 3)

    def test_loop_ends_as_soon_as_the_required_tool_succeeds(self):
        fake = FakeChat([tool_request("cost_per_use", GOOD_COST_ARGS), "never requested"])
        trace = run_tool_phase(start_messages(), chat=fake, required=("cost_per_use",))

        self.assertEqual(trace["stopped"], "requirements_met")
        self.assertEqual(len(fake.calls), 1)  # the model was not asked "are you done?"

    def test_loop_keeps_going_when_a_call_in_the_turn_failed(self):
        bad = {"price": 600}
        fake = FakeChat([tool_request("cost_per_use", bad), tool_request("cost_per_use", GOOD_COST_ARGS), "x"])
        trace = run_tool_phase(start_messages(), chat=fake, required=("cost_per_use",))

        self.assertEqual(trace["stopped"], "requirements_met")
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual([c["ok"] for c in trace["tool_calls"]], [False, True])

    def test_an_identical_repeat_is_not_run_again_and_ends_the_loop(self):
        # Same arguments, different key order: still counts as the same call.
        same_call_reordered = {"years": 2, "uses_per_week": 5, "price": 600}
        fake = FakeChat([
            tool_request("cost_per_use", GOOD_COST_ARGS),
            tool_request("cost_per_use", same_call_reordered),
            "this reply should never be requested",
        ])
        messages = start_messages()
        trace = run_tool_phase(messages, chat=fake)

        self.assertEqual(trace["stopped"], "repeating")
        self.assertEqual([c["duplicate"] for c in trace["tool_calls"]], [False, True])
        self.assertEqual(len(fake.calls), 2)  # the loop stopped instead of asking a third time
        # The repeat was answered with a pointer back to the first result, not run a second time.
        self.assertIn("already made this exact call", messages[-1]["content"])

    def test_a_turn_with_one_new_call_and_one_repeat_keeps_going(self):
        fake = FakeChat([
            tool_request("cost_per_use", GOOD_COST_ARGS),
            tool_request("cost_per_use", {**GOOD_COST_ARGS, "years": 3}),
            "Done.",
        ])
        trace = run_tool_phase(start_messages(), chat=fake)
        self.assertEqual(trace["stopped"], "model_finished")
        self.assertEqual([c["duplicate"] for c in trace["tool_calls"]], [False, False])

    def test_no_tool_needed_is_fine_when_nothing_is_required(self):
        fake = FakeChat(["Nothing to calculate."])
        trace = run_tool_phase(start_messages(), chat=fake)
        self.assertEqual(trace["tool_calls"], [])
        self.assertEqual(trace["stopped"], "model_finished")


class SafetyLimits(unittest.TestCase):
    def test_every_call_has_a_hard_cap_on_reply_length(self):
        fake = FakeChat([tool_request("cost_per_use", GOOD_COST_ARGS), json.dumps(valid_take())])
        purchase = Purchase(item="Headphones", price=350, why="Loud commute", want_level=7)
        open_turn(ANALYST, purchase, chat=fake)

        caps = [call["options"]["num_predict"] for call in fake.calls]
        self.assertEqual(caps, [config.MAX_TOOL_TURN_TOKENS, config.MAX_ANSWER_TOKENS])

    def test_tool_turns_run_cold_and_the_answer_runs_warm(self):
        fake = FakeChat([tool_request("cost_per_use", GOOD_COST_ARGS), json.dumps(valid_take())])
        purchase = Purchase(item="Headphones", price=350, why="Loud commute", want_level=7)
        open_turn(ANALYST, purchase, chat=fake)

        self.assertEqual(fake.calls[0]["options"]["temperature"], config.TOOL_TEMPERATURE)
        self.assertEqual(fake.calls[1]["options"]["temperature"], config.TEMPERATURE)

    def test_a_cut_off_tool_turn_is_flagged_in_the_trace(self):
        fake = FakeChat([cut_off("I will now think about")])
        trace = run_tool_phase(start_messages(), chat=fake)
        self.assertTrue(trace["model_calls"][0]["cut_off"])

    def test_a_cut_off_answer_is_retried_with_a_length_hint(self):
        truncated = json.dumps(valid_take())[:60]
        fake = FakeChat([cut_off(truncated), json.dumps(valid_take())])
        take, attempts = call_structured_from_messages(start_messages(), ANALYST.take_schema, chat=fake)

        self.assertTrue(attempts[0]["cut_off"])
        self.assertFalse(attempts[1]["cut_off"])
        self.assertIn("length limit", fake.calls[1]["messages"][-1]["content"])

    def test_the_default_client_has_a_timeout(self):
        from agents.base import client

        self.assertEqual(client._client.timeout.read, config.REQUEST_TIMEOUT_SECONDS)


class AnalystWithTools(unittest.TestCase):
    purchase = Purchase(item="Headphones", price=350, why="Loud commute", want_level=7)

    def test_two_phases_in_order_and_tools_are_not_sent_to_the_final_answer(self):
        resale_args = {"price": 350, "category": "audio", "years_owned": 3}
        cost_args = {"price": 350, "uses_per_week": 10, "years": 3, "category": "audio"}
        fake = FakeChat([
            tool_request("estimate_resale", resale_args),
            tool_request("cost_per_use", cost_args),
            json.dumps(valid_take()),
        ])
        take, trace, _ = open_turn(ANALYST, self.purchase, chat=fake)

        self.assertEqual(take.lean, "buy")
        self.assertEqual([c["tool"] for c in trace["tool_calls"]], ["estimate_resale", "cost_per_use"])
        self.assertEqual(trace["tool_phase"]["missing_required"], [])
        # Gather calls carry tools and no format. The final call carries a format and no tools.
        self.assertEqual(trace["tool_phase"]["stopped"], "requirements_met")
        for gather_call in fake.calls[:2]:
            self.assertIn("tools", gather_call)
            self.assertNotIn("format", gather_call)
        final_call = fake.calls[2]
        self.assertIn("format", final_call)
        self.assertNotIn("tools", final_call)
        # The final call can see the tool results, and ends by asking for the answer.
        roles = [m["role"] for m in final_call["messages"]]
        self.assertEqual(roles.count("tool"), 2)
        self.assertIn("final reply", final_call["messages"][-1]["content"])

    def test_tool_instructions_only_appear_when_tools_are_on(self):
        self.assertIn("cost_per_use", ANALYST.system_prompt(use_tools=True))
        self.assertNotIn("cost_per_use", ANALYST.system_prompt(use_tools=False))

    def test_without_tools_there_is_only_the_final_call(self):
        fake = FakeChat([json.dumps(valid_take())])
        take, trace, _ = open_turn(ANALYST, self.purchase, use_tools=False, chat=fake)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(trace["tool_calls"], [])


if __name__ == "__main__":
    unittest.main()
