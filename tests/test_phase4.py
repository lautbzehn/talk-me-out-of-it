"""Phase 4 tests: the shared council agent, the four rating agents, and the rules
every take must pass. None of them call the real model.

Run with:  .venv/bin/python -m unittest -v
"""

import json
import unittest
from dataclasses import replace

from pydantic import ValidationError

from agents.alternatives_hunter import ALTERNATIVES_HUNTER
from agents.analyst import ANALYST
from agents.base import StructuredOutputError
from agents.budget_guardian import BUDGET_GUARDIAN
from agents.council_agent import HARD_RULES, CouncilAgent, open_turn
from agents.future_you import FUTURE_YOU
from agents.roster import COUNCIL
from agents.schemas import AgentTake, AnalystRatings, Purchase, Rating
from tests.helpers import FakeChat, tool_request
from tests.test_phase2 import valid_take

COST_ARGS = {"price": 350, "uses_per_week": 10, "years": 3, "category": "audio"}
USED_ARGS = {"price": 350, "category": "audio", "years_owned": 1}
PURCHASE = Purchase(item="Headphones", price=350, why="Loud commute", want_level=7)

# The Analyst's rubric with no tools, standing in for agents like Future You.
NO_TOOLS = replace(ANALYST, name="The Test Agent", tool_names=(), required_tools=())


def take_for(agent, **changes) -> dict:
    """A correct reply for any agent's rubric. Tests pass `changes` to break one piece of it."""
    data = {
        "take": "This is a fair purchase for what you described. Still, it deserves a second look first.",
        "ratings": {
            name: {"reason": "A rough read on this point, unverified where it depends on timing.", "score": 5}
            for name in agent.ratings.model_fields
        },
        "lean": "wait",
        "confidence": 6,
    }
    data.update(changes)
    return data


class AgentDefinition(unittest.TestCase):
    def test_prompt_has_the_shared_rules_and_this_agents_own_parts(self):
        prompt = ANALYST.system_prompt()
        self.assertIn("You are The Analyst", prompt)
        self.assertIn(ANALYST.focus, prompt)
        self.assertIn(ANALYST.voice, prompt)
        for rule in HARD_RULES:
            self.assertIn(rule, prompt)
        for name, field in AnalystRatings.model_fields.items():
            self.assertIn(f"- {name}: {field.description}", prompt)

    def test_extra_rules_appear_only_for_their_agent(self):
        strict = replace(ANALYST, extra_rules=("Never compare it with other products.",))
        self.assertIn("- Never compare it with other products.", strict.system_prompt())
        self.assertNotIn("Never compare it with other products.", ANALYST.system_prompt())

    def test_an_agent_without_tools_gets_no_tool_instructions(self):
        self.assertNotIn("calculator tools", NO_TOOLS.system_prompt())
        self.assertIn("calculator tools", ANALYST.system_prompt())

    def test_an_unknown_tool_is_caught_when_the_agent_is_defined(self):
        with self.assertRaises(ValueError) as caught:
            replace(ANALYST, tool_names=("buy_it_now",), required_tools=())
        self.assertIn("buy_it_now", str(caught.exception))

    def test_a_required_tool_must_be_one_the_agent_can_call(self):
        with self.assertRaises(ValueError):
            CouncilAgent(
                name="Broken", focus="x", voice="x", ratings=AnalystRatings,
                tool_names=("estimate_resale",), required_tools=("cost_per_use",),
            )

    def test_take_schema_is_the_shared_shape_with_this_agents_rubric(self):
        self.assertIs(ANALYST.take_schema, AgentTake[AnalystRatings])
        rubric = ANALYST.take_schema.model_json_schema()["$defs"]["AnalystRatings"]["properties"]
        self.assertEqual(list(rubric), ["value_per_use", "longevity", "upgrade_gap"])


class TakeLength(unittest.TestCase):
    def test_a_one_line_take_is_rejected(self):
        with self.assertRaises(ValidationError):
            ANALYST.take_schema.model_validate(valid_take(take="Too expensive for what it does."))

    def test_a_two_sentence_take_passes(self):
        take = "You would pay about a dollar per commute. That is fair for something you use daily."
        ANALYST.take_schema.model_validate(valid_take(take=take))

    def test_one_long_sentence_is_rejected(self):
        # The exact take that slipped through the 60 character rule in the milestone 1 live run.
        take = "High-quality headphones could significantly improve your daily commute experience."
        with self.assertRaises(ValidationError) as caught:
            ANALYST.take_schema.model_validate(valid_take(take=take))
        self.assertIn("two full sentences", str(caught.exception))

    def test_a_price_with_cents_is_not_a_sentence_break(self):
        take = "At $0.22 per use and $9.72 per month this is cheap for something you use every day"
        with self.assertRaises(ValidationError):
            ANALYST.take_schema.model_validate(valid_take(take=take))

    def test_the_last_sentence_needs_no_final_period(self):
        take = "You would pay about $0.22 per use. That is fair for a daily commute"
        ANALYST.take_schema.model_validate(valid_take(take=take))

    def test_a_sentence_ending_in_a_quote_still_counts(self):
        take = 'I keep saying "I use it every day." It earned its place on my desk.'
        FUTURE_YOU.take_schema.model_validate(take_for(FUTURE_YOU, take=take))


class ScoreInsideReason(unittest.TestCase):
    def test_a_score_anywhere_in_a_reason_is_rejected(self):
        leaks = [
            "Minor gains over the PS5, so 6/10 for significant improvement.",  # from the live run
            "Your want level of 8/10 is high for this reason.",
            "I would call it 7 out of 10 for daily use.",
            "Decent value at roughly 7.5/10 overall.",
        ]
        for leaked in leaks:
            with self.subTest(reason=leaked):
                with self.assertRaises(ValidationError):
                    Rating(reason=leaked, score=6)

    def test_other_numbers_with_a_slash_are_fine(self):
        for fine in ["Built to run 24/7 without trouble.", "A used one costs 1/10th of new, roughly."]:
            with self.subTest(reason=fine):
                Rating(reason=fine, score=6)


class OpenTurn(unittest.TestCase):
    def test_an_agent_without_tools_answers_in_one_call(self):
        fake = FakeChat([json.dumps(valid_take())])
        take, trace, conversation = open_turn(NO_TOOLS, PURCHASE, chat=fake)

        self.assertEqual(take.lean, "buy")
        self.assertEqual(len(fake.calls), 1)
        self.assertNotIn("tools", fake.calls[0])
        self.assertIn("format", fake.calls[0])
        self.assertIsNone(trace["tool_phase"])
        self.assertEqual(trace["tool_calls"], [])

    def test_conversation_keeps_the_tool_work_and_ends_with_the_answer(self):
        fake = FakeChat([tool_request("cost_per_use", COST_ARGS), "not json", json.dumps(valid_take())])
        take, trace, conversation = open_turn(ANALYST, PURCHASE, chat=fake)

        roles = [message["role"] for message in conversation]
        self.assertEqual(roles, ["system", "user", "assistant", "tool", "user", "assistant"])
        self.assertEqual(conversation[4]["content"], ANALYST.after_tools)
        self.assertEqual(conversation[-1]["content"], json.dumps(valid_take()))
        # The rejected attempt is in the trace, but not in the conversation later rounds will continue.
        self.assertEqual([a["ok"] for a in trace["attempts"]], [False, True])
        self.assertNotIn("not json", [message["content"] for message in conversation])

    def test_a_failed_answer_still_keeps_the_tool_work_on_record(self):
        fake = FakeChat([tool_request("cost_per_use", COST_ARGS), "bad", "bad", "bad"])
        with self.assertRaises(StructuredOutputError) as caught:
            open_turn(ANALYST, PURCHASE, chat=fake)

        trace = caught.exception.trace
        self.assertEqual([call["tool"] for call in trace["tool_calls"]], ["cost_per_use"])
        self.assertEqual(trace["tool_phase"]["missing_required"], [])
        self.assertEqual(len(trace["attempts"]), 3)

    def test_every_agent_reads_the_same_purchase_prompt(self):
        with_tools = FakeChat([tool_request("cost_per_use", COST_ARGS), json.dumps(valid_take())])
        without_tools = FakeChat([json.dumps(valid_take())])
        open_turn(ANALYST, PURCHASE, chat=with_tools)
        open_turn(NO_TOOLS, PURCHASE, chat=without_tools)

        first = with_tools.calls[0]["messages"][1]["content"]
        self.assertEqual(first, without_tools.calls[0]["messages"][1]["content"])
        self.assertIn("$350.00", first)
        self.assertIn("nothing, this would be a new device", first)



class Council(unittest.TestCase):
    def test_speaking_order(self):
        names = [agent.name for agent in COUNCIL]
        self.assertEqual(names, ["The Analyst", "Future You", "Budget Guardian", "Alternatives Hunter"])

    def test_every_agent_has_its_own_three_item_rubric(self):
        self.assertEqual(len({agent.ratings for agent in COUNCIL}), 4)
        for agent in COUNCIL:
            fields = agent.ratings.model_fields
            self.assertEqual(len(fields), 3, agent.name)
            for name, field in fields.items():
                with self.subTest(agent=agent.name, item=name):
                    self.assertIs(field.annotation, Rating)
                    # Every guide states both ends in the shared direction: 10 favors buying.
                    self.assertRegex(field.description, r"^10 = .+ 1 = ")

    def test_rubric_keys(self):
        keys = {agent.name: list(agent.ratings.model_fields) for agent in COUNCIL}
        self.assertEqual(keys, {
            "The Analyst": ["value_per_use", "longevity", "upgrade_gap"],
            "Future You": ["six_month_glow", "want_vs_reason", "use_reality"],
            "Budget Guardian": ["price_for_the_problem", "cost_of_waiting", "better_than_keeping_it"],
            "Alternatives Hunter": ["worth_full_price", "release_timing", "ecosystem_freedom"],
        })

    def test_no_rubric_key_is_a_double_negative(self):
        # The model scored "no_cheaper_path" backwards in every live run. 10 always favors
        # buying, so a key should name the thing that favors buying.
        for agent in COUNCIL:
            for name in agent.ratings.model_fields:
                self.assertFalse(name.startswith("no_"), f"{agent.name}: {name}")

    def test_rubric_items_never_share_a_name(self):
        # Scoring and the UI key ratings by name, so two agents must never reuse one.
        names = [name for agent in COUNCIL for name in agent.ratings.model_fields]
        self.assertEqual(len(names), len(set(names)))

    def test_every_prompt_has_the_hard_rules_its_own_rules_and_its_rubric(self):
        for agent in COUNCIL:
            prompt = agent.system_prompt()
            with self.subTest(agent=agent.name):
                self.assertIn(f"You are {agent.name}", prompt)
                for rule in (*HARD_RULES, *agent.extra_rules):
                    self.assertIn(f"- {rule}", prompt)
                for name, field in agent.ratings.model_fields.items():
                    self.assertIn(f"- {name}: {field.description}", prompt)

    def test_who_must_use_which_tool(self):
        required = {agent.name: agent.required_tools for agent in COUNCIL}
        self.assertEqual(required, {
            "The Analyst": ("cost_per_use",),
            "Future You": (),
            "Budget Guardian": (),
            "Alternatives Hunter": ("estimate_resale",),
        })

    def test_every_agent_answers_through_the_same_turn(self):
        for agent in COUNCIL:
            with self.subTest(agent=agent.name):
                gather = {
                    "The Analyst": [tool_request("cost_per_use", COST_ARGS)],
                    "Alternatives Hunter": [tool_request("estimate_resale", USED_ARGS)],
                }.get(agent.name, [])
                fake = FakeChat([*gather, json.dumps(take_for(agent))])
                take, trace, conversation = open_turn(agent, PURCHASE, chat=fake)

                self.assertEqual(take.lean, "wait")
                self.assertEqual(len(fake.calls), len(gather) + 1)
                self.assertEqual(conversation[-1]["role"], "assistant")
                if gather:
                    self.assertEqual(trace["tool_phase"]["stopped"], "requirements_met")
                else:
                    self.assertIsNone(trace["tool_phase"])
                    self.assertNotIn("tools", fake.calls[0])


class AgentVoices(unittest.TestCase):
    def test_future_you_speaks_in_first_person_and_invents_no_news(self):
        prompt = FUTURE_YOU.system_prompt()
        self.assertIn("first person", prompt)
        self.assertIn("Never invent news", prompt)

    def test_budget_guardian_never_guesses_income(self):
        prompt = BUDGET_GUARDIAN.system_prompt()
        self.assertIn("do not know their income", prompt)
        self.assertIn("Never tell them what to do with the money instead", prompt)

    def test_no_agent_may_work_out_its_own_dollar_amounts(self):
        for agent in COUNCIL:
            self.assertIn("Never work out a new dollar amount yourself.", agent.system_prompt(), agent.name)

    def test_future_you_has_no_example_lines_to_copy(self):
        # The model pasted an example line word for word in the first live run.
        self.assertNotIn("reach for it", FUTURE_YOU.system_prompt())

    def test_alternatives_hunter_is_told_to_use_one_year_resale(self):
        self.assertIn("years_owned of 1", ALTERNATIVES_HUNTER.system_prompt())

    def test_code_labels_release_timing_unverified_when_the_model_forgets(self):
        schema = ALTERNATIVES_HUNTER.take_schema
        unlabeled = take_for(ALTERNATIVES_HUNTER)
        unlabeled["ratings"]["release_timing"] = {"reason": "A new model is due next spring.", "score": 3}
        take = schema.model_validate(unlabeled)
        self.assertEqual(take.ratings.release_timing.reason, "Unverified: A new model is due next spring.")

        labeled = take_for(ALTERNATIVES_HUNTER)
        labeled["ratings"]["release_timing"] = {"reason": "Unverified, but this kind refreshes yearly.", "score": 4}
        take = schema.model_validate(labeled)
        self.assertEqual(take.ratings.release_timing.reason, "Unverified, but this kind refreshes yearly.")

    def test_a_label_that_would_not_fit_is_still_asked_for(self):
        # 195 characters: the label would push it past the 200-character limit, so the old rule asks the model.
        long_reason = ("A newer model seems likely soon. " * 6)[:194] + "."
        self.assertEqual(len(long_reason), 195)
        unlabeled = take_for(ALTERNATIVES_HUNTER)
        unlabeled["ratings"]["release_timing"] = {"reason": long_reason, "score": 3}
        with self.assertRaises(ValidationError) as caught:
            ALTERNATIVES_HUNTER.take_schema.model_validate(unlabeled)
        self.assertIn("release timing is unverified", str(caught.exception))

    def test_a_missing_label_costs_no_retry(self):
        # In the repeated 14B run this was the most common rejection: 16 retries for one missing word.
        unlabeled = take_for(ALTERNATIVES_HUNTER)
        unlabeled["ratings"]["release_timing"] = {"reason": "A new model is due next spring.", "score": 3}
        fake = FakeChat([tool_request("estimate_resale", USED_ARGS), json.dumps(unlabeled)])
        take, trace, _ = open_turn(ALTERNATIVES_HUNTER, PURCHASE, chat=fake)

        self.assertEqual([a["ok"] for a in trace["attempts"]], [True])
        self.assertTrue(take.ratings.release_timing.reason.startswith("Unverified: "))



class ToolWording(unittest.TestCase):
    def test_one_year_is_singular(self):
        from tools.resale import ResaleInput, estimate_resale

        summary = estimate_resale(ResaleInput(price=700, category="console", years_owned=1))["summary"]
        self.assertIn("after 1 year.", summary)


if __name__ == "__main__":
    unittest.main()
