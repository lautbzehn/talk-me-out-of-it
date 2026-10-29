"""Phase 4 tests, milestone 3: the rebuttal schema, the digest, changes, and the two round runners.
None of them call the real model.

Run with:  .venv/bin/python -m unittest -v
"""

import json
import typing
import unittest

from pydantic import ValidationError

import config
from agents.alternatives_hunter import ALTERNATIVES_HUNTER
from agents.analyst import ANALYST
from agents.base import StructuredOutputError
from agents.budget_guardian import BUDGET_GUARDIAN
from agents.council_agent import open_turn, rebuttal_turn
from agents.future_you import FUTURE_YOU
from agents.roster import COUNCIL
from agents.schemas import AgentName, is_addressed
from council import CouncilError, run_opening_round, run_rebuttal_round
from debate import Debate, Round, Turn, compute_changes, render_round
from tests.helpers import FakeChat, tool_request
from tests.test_phase4 import COST_ARGS, PURCHASE, USED_ARGS, take_for

OTHERS = ["Future You", "Budget Guardian", "Alternatives Hunter"]  # who The Analyst can answer


def rebuttal_for(agent, responding_to, **changes) -> dict:
    """A correct rebuttal for any agent. The response names the first agent it answers."""
    data = {
        "responding_to": responding_to,
        "response": f"{(responding_to or ['Everyone'])[0]}, that is a fair point, but I still see this one differently.",
        "ratings": {
            name: {"reason": "Still a rough read, unverified where it depends on timing.", "score": 6}
            for name in agent.ratings.model_fields
        },
        "lean": "wait",
        "confidence": 7,
    }
    data.update(changes)
    return data


def opening_replies(analyst_lean="buy") -> list:
    """Scripted model replies for a full opening round, in speaking order."""
    return [
        tool_request("cost_per_use", COST_ARGS),
        json.dumps(take_for(ANALYST, lean=analyst_lean)),
        json.dumps(take_for(FUTURE_YOU)),
        json.dumps(take_for(BUDGET_GUARDIAN)),
        tool_request("estimate_resale", USED_ARGS),
        json.dumps(take_for(ALTERNATIVES_HUNTER)),
    ]


def rebuttal_replies(agents=COUNCIL) -> list:
    """One valid rebuttal per agent, each answering the first other agent in speaking order."""
    replies = []
    for agent in agents:
        target = next(other.name for other in agents if other.name != agent.name)
        replies.append(json.dumps(rebuttal_for(agent, [target])))
    return replies


def validate(agent, data, me="The Analyst", speakers=OTHERS):
    return agent.rebuttal_schema.model_validate(data, context={"self": me, "speakers": speakers})


class RebuttalRules(unittest.TestCase):
    def test_a_valid_rebuttal_passes(self):
        rebuttal = validate(ANALYST, rebuttal_for(ANALYST, ["Future You"]))
        self.assertEqual(rebuttal.responding_to, ["Future You"])

    def test_answering_yourself_is_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            validate(ANALYST, rebuttal_for(ANALYST, ["The Analyst"], response="The Analyst, I agree with myself here."))
        self.assertIn("not yourself", str(caught.exception))

    def test_answering_someone_who_did_not_speak_is_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            validate(ANALYST, rebuttal_for(ANALYST, ["Future You"]), speakers=["Budget Guardian"])
        self.assertIn("did not speak last round", str(caught.exception))

    def test_an_unknown_name_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate(ANALYST, rebuttal_for(ANALYST, ["The Judge"], response="The Judge, you are wrong here."))

    def test_answering_nobody_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate(ANALYST, rebuttal_for(ANALYST, [], response="Nobody in particular said anything useful."))

    def test_the_response_must_name_who_it_answers(self):
        data = rebuttal_for(ANALYST, ["Budget Guardian"], response="I still think the numbers speak for themselves.")
        with self.assertRaises(ValidationError) as caught:
            validate(ANALYST, data)
        self.assertIn("response", str(caught.exception))
        self.assertIn("by name", str(caught.exception))

    def test_short_names_count_but_a_bare_you_does_not(self):
        self.assertTrue(is_addressed("The Analyst", "Analyst, your math is fine."))
        self.assertTrue(is_addressed("Budget Guardian", "I hear the guardian on this."))
        self.assertTrue(is_addressed("Alternatives Hunter", "Hunter, a refurbished one is a fair idea."))
        self.assertTrue(is_addressed("Future You", "Future You, I think you are too hopeful."))
        self.assertFalse(is_addressed("Future You", "You will use it every day."))

    def test_repeated_names_are_kept_once(self):
        rebuttal = validate(ANALYST, rebuttal_for(ANALYST, ["Future You", "Future You"]))
        self.assertEqual(rebuttal.responding_to, ["Future You"])

    def test_answering_everyone_is_rejected(self):
        # In the first live run every rebuttal answered all three others, as a summary.
        with self.assertRaises(ValidationError):
            validate(ANALYST, rebuttal_for(ANALYST, OTHERS))

    def test_without_context_only_the_shape_is_checked(self):
        ANALYST.rebuttal_schema.model_validate(rebuttal_for(ANALYST, ["Future You"]))

    def test_rubric_rules_still_apply_in_a_rebuttal(self):
        data = rebuttal_for(ALTERNATIVES_HUNTER, ["The Analyst"])
        data["ratings"]["release_timing"] = {"reason": "A new one is due next spring.", "score": 3}
        rebuttal = validate(ALTERNATIVES_HUNTER, data, me="Alternatives Hunter", speakers=["The Analyst"])
        self.assertEqual(rebuttal.ratings.release_timing.reason, "Unverified: A new one is due next spring.")

        data["ratings"]["worth_full_price"] = {"reason": "Worth about 6/10 at full price.", "score": 6}
        with self.assertRaises(ValidationError):
            validate(ALTERNATIVES_HUNTER, data, me="Alternatives Hunter", speakers=["The Analyst"])

    def test_agent_names_match_the_roster(self):
        self.assertEqual(typing.get_args(AgentName), tuple(agent.name for agent in COUNCIL))


def opening_round() -> Round:
    """A finished opening round: the Analyst with a tool result, Future You failed, the Guardian answered."""
    analyst_take = ANALYST.take_schema.model_validate(take_for(ANALYST, lean="buy"))
    guardian_take = BUDGET_GUARDIAN.take_schema.model_validate(take_for(BUDGET_GUARDIAN))
    tool_call = {"ok": True, "duplicate": False, "result": {"summary": "Net cost $172.99, about $0.11 per use."}}
    return Round(number=1, kind="opening", turns=[
        Turn("The Analyst", "ok", analyst_take, {"tool_calls": [tool_call]}),
        Turn("Future You", "failed", None, {"tool_calls": [], "attempts": []}),
        Turn("Budget Guardian", "ok", guardian_take, {"tool_calls": []}),
    ])


class Digest(unittest.TestCase):
    def test_the_reader_does_not_see_its_own_turn(self):
        digest = render_round(opening_round(), exclude="Budget Guardian")
        self.assertIn("The Analyst leaned BUY", digest)
        self.assertNotIn("Budget Guardian leaned", digest)

    def test_tool_results_are_included_so_others_can_cite_them(self):
        digest = render_round(opening_round(), exclude="Budget Guardian")
        self.assertIn("Tool result: Net cost $172.99, about $0.11 per use.", digest)

    def test_a_failed_turn_says_so(self):
        self.assertIn("(Future You did not answer this round.)", render_round(opening_round()))

    def test_every_rating_is_listed_with_its_score_and_reason(self):
        digest = render_round(opening_round())
        self.assertIn("  value_per_use 5: A rough read on this point", digest)
        self.assertIn("  better_than_keeping_it 5:", digest)

    def test_no_raw_json_reaches_another_agent(self):
        digest = render_round(opening_round())
        self.assertNotIn("{", digest)
        self.assertNotIn('"ratings"', digest)

    def test_a_rebuttal_shows_who_it_answered_and_what_moved(self):
        before = ANALYST.take_schema.model_validate(take_for(ANALYST, lean="buy"))
        after = ANALYST.rebuttal_schema.model_validate(rebuttal_for(ANALYST, ["Future You"]))
        turn = Turn("The Analyst", "ok", after, {"tool_calls": []}, changes=compute_changes(before, after))
        text = render_round(Round(number=2, kind="rebuttal", turns=[turn]))

        self.assertIn("The Analyst, answering Future You, now leans WAIT (confidence 7, was BUY)", text)
        self.assertIn("value_per_use 6 (was 5):", text)


class Changes(unittest.TestCase):
    def test_changes_are_computed_from_the_numbers(self):
        before = ANALYST.take_schema.model_validate(take_for(ANALYST, lean="buy"))
        after_data = rebuttal_for(ANALYST, ["Future You"])
        after_data["ratings"]["longevity"]["score"] = 5  # unchanged from the take
        changes = compute_changes(before, ANALYST.rebuttal_schema.model_validate(after_data))

        self.assertEqual(changes["ratings"]["value_per_use"], {"from": 5, "to": 6})
        self.assertEqual(changes["ratings"]["longevity"], {"from": 5, "to": 5})
        self.assertEqual(changes["lean"], {"from": "buy", "to": "wait"})
        self.assertTrue(changes["changed_mind"])
        self.assertEqual(changes["scores_moved"], 2)

    def test_same_lean_is_not_a_change_of_mind(self):
        before = ANALYST.take_schema.model_validate(take_for(ANALYST, lean="wait"))
        after = ANALYST.rebuttal_schema.model_validate(rebuttal_for(ANALYST, ["Future You"]))
        self.assertFalse(compute_changes(before, after)["changed_mind"])


class RebuttalTurn(unittest.TestCase):
    def setUp(self):
        opening = FakeChat(opening_replies()[:2])
        _, _, self.conversation = open_turn(ANALYST, PURCHASE, chat=opening)
        self.digest = render_round(opening_round(), exclude="The Analyst")

    def test_it_continues_the_agents_own_conversation(self):
        fake = FakeChat([json.dumps(rebuttal_for(ANALYST, ["Budget Guardian"]))])
        before = list(self.conversation)
        rebuttal, trace, conversation = rebuttal_turn(ANALYST, self.conversation, self.digest, ["Budget Guardian"], chat=fake)

        sent = fake.calls[0]["messages"]
        self.assertEqual(sent[:len(before)], before)  # system prompt, purchase, tools, its own answer
        self.assertIn(self.digest, sent[-1]["content"])
        self.assertEqual(self.conversation, before)  # the caller's list is not changed
        self.assertEqual(conversation[-1]["role"], "assistant")
        self.assertEqual(rebuttal.responding_to, ["Budget Guardian"])

    def test_the_prompt_restates_who_the_agent_is(self):
        fake = FakeChat([json.dumps(rebuttal_for(ALTERNATIVES_HUNTER, ["The Analyst"]))])
        rebuttal_turn(ALTERNATIVES_HUNTER, self.conversation, self.digest, ["The Analyst"], chat=fake)

        prompt = fake.calls[0]["messages"][-1]["content"]
        self.assertIn("You are still Alternatives Hunter.", prompt)
        self.assertIn(ALTERNATIVES_HUNTER.voice, prompt)
        self.assertIn("Only Future You speaks as the user.", prompt)

    def test_one_call_no_tools_warm_temperature_and_the_rebuttal_shape(self):
        fake = FakeChat([json.dumps(rebuttal_for(ANALYST, ["Budget Guardian"]))])
        rebuttal_turn(ANALYST, self.conversation, self.digest, ["Budget Guardian"], chat=fake)

        call = fake.calls[0]
        self.assertEqual(len(fake.calls), 1)
        self.assertNotIn("tools", call)
        self.assertEqual(list(call["format"]["properties"])[:2], ["responding_to", "response"])
        self.assertEqual(call["options"]["temperature"], config.TEMPERATURE)

    def test_answering_yourself_is_sent_back_and_fixed(self):
        bad = rebuttal_for(ANALYST, ["The Analyst"], response="The Analyst, I stand by what I said before.")
        fake = FakeChat([json.dumps(bad), json.dumps(rebuttal_for(ANALYST, ["Budget Guardian"]))])
        rebuttal, trace, _ = rebuttal_turn(ANALYST, self.conversation, self.digest, ["Budget Guardian"], chat=fake)

        self.assertEqual([a["ok"] for a in trace["attempts"]], [False, True])
        self.assertIn("not yourself", fake.calls[1]["messages"][-1]["content"])

    def test_a_failed_rebuttal_keeps_its_attempts_on_record(self):
        fake = FakeChat(["bad"] * config.MAX_ATTEMPTS)
        with self.assertRaises(StructuredOutputError) as caught:
            rebuttal_turn(ANALYST, self.conversation, self.digest, ["Budget Guardian"], chat=fake)
        self.assertEqual(len(caught.exception.trace["attempts"]), config.MAX_ATTEMPTS)


def system_names(fake: FakeChat, calls: slice) -> list[str]:
    """Which agent each recorded call came from, read from the start of its system prompt."""
    return [call["messages"][0]["content"].split(",")[0].removeprefix("You are ") for call in fake.calls[calls]]


class Rounds(unittest.TestCase):
    def test_opening_round_runs_every_agent_in_speaking_order(self):
        events = []
        debate = Debate(PURCHASE)
        fake = FakeChat(opening_replies())
        current = run_opening_round(debate, chat=fake, on_event=events.append)

        self.assertEqual([turn.agent for turn in current.turns], [agent.name for agent in COUNCIL])
        self.assertTrue(all(turn.status == "ok" for turn in current.turns))
        self.assertEqual(len(current.turns[0].trace["tool_calls"]), 1)
        self.assertEqual(debate.rounds, [current])
        kinds = [event["event"] for event in events]
        self.assertEqual(kinds, [
            "round_start",
            "agent_start", "tool_call", "agent_done",  # The Analyst uses cost_per_use
            "agent_start", "agent_done",
            "agent_start", "agent_done",
            "agent_start", "tool_call", "agent_done",  # Alternatives Hunter uses estimate_resale
            "round_done",
        ])
        tool_events = [event for event in events if event["event"] == "tool_call"]
        self.assertEqual([(e["agent"], e["tool"]) for e in tool_events],
                         [("The Analyst", "cost_per_use"), ("Alternatives Hunter", "estimate_resale")])
        self.assertIn("per use", tool_events[0]["summary"])

    def test_an_agent_that_fails_sits_out_and_the_others_carry_on(self):
        replies = opening_replies()
        replies[2:3] = ["bad"] * config.MAX_ATTEMPTS  # Future You never gives valid JSON
        debate = Debate(PURCHASE)
        current = run_opening_round(debate, chat=FakeChat(replies))

        self.assertEqual([turn.status for turn in current.turns], ["ok", "failed", "ok", "ok"])
        self.assertEqual(len(current.turns[1].trace["attempts"]), config.MAX_ATTEMPTS)

    def test_rebuttal_round_gives_each_agent_the_others_turns(self):
        debate = Debate(PURCHASE)
        fake = FakeChat(opening_replies() + rebuttal_replies())
        run_opening_round(debate, chat=fake)
        current = run_rebuttal_round(debate, chat=fake)

        self.assertEqual(current.number, 2)
        self.assertEqual(system_names(fake, slice(6, 10)), [agent.name for agent in COUNCIL])
        for call, agent in zip(fake.calls[6:10], COUNCIL):
            digest = call["messages"][-1]["content"]
            with self.subTest(reader=agent.name):
                self.assertNotIn(f"{agent.name} leaned", digest)
                for other in COUNCIL:
                    if other is not agent:
                        self.assertIn(f"{other.name} leaned", digest)

    def test_changes_are_ready_when_the_agent_done_event_fires(self):
        events = []
        debate = Debate(PURCHASE)
        fake = FakeChat(opening_replies(analyst_lean="buy") + rebuttal_replies())
        run_opening_round(debate, chat=fake)
        run_rebuttal_round(debate, chat=fake, on_event=events.append)

        analyst_done = next(e for e in events if e["event"] == "agent_done" and e["agent"] == "The Analyst")
        self.assertEqual(analyst_done["turn"].changes["lean"], {"from": "buy", "to": "wait"})
        self.assertTrue(analyst_done["turn"].changes["changed_mind"])

    def test_a_failed_agent_sits_out_the_rebuttal_and_cannot_be_answered(self):
        replies = opening_replies()
        replies[2:3] = ["bad"] * config.MAX_ATTEMPTS  # Future You fails the opening round
        still_in = [ANALYST, BUDGET_GUARDIAN, ALTERNATIVES_HUNTER]
        answers_future_you = rebuttal_for(ANALYST, ["Future You"])
        rebuttals = [json.dumps(answers_future_you), *rebuttal_replies(still_in)]
        debate = Debate(PURCHASE)
        fake = FakeChat(replies + rebuttals)
        run_opening_round(debate, chat=fake)
        current = run_rebuttal_round(debate, chat=fake)

        self.assertEqual([turn.agent for turn in current.turns], [agent.name for agent in still_in])
        analyst = current.turns[0]
        self.assertEqual([a["ok"] for a in analyst.trace["attempts"]], [False, True])
        self.assertIn("did not speak last round", analyst.trace["attempts"][0]["error"])

    def test_fewer_than_two_answers_stops_the_council(self):
        debate = Debate(PURCHASE, rounds=[Round(1, "opening", [Turn("The Analyst", "ok", None, {})])])
        with self.assertRaises(CouncilError):
            run_rebuttal_round(debate, chat=FakeChat([]))
        self.assertEqual(len(debate.rounds), 1)  # no empty round was started

    def test_a_tiebreak_continues_from_the_rebuttal(self):
        debate = Debate(PURCHASE)
        fake = FakeChat(opening_replies() + rebuttal_replies() + rebuttal_replies())
        run_opening_round(debate, chat=fake)
        second = run_rebuttal_round(debate, chat=fake)
        third = run_rebuttal_round(debate, kind="tiebreak", chat=fake)

        self.assertEqual((third.number, third.kind), (3, "tiebreak"))
        analyst_round_3 = fake.calls[10]["messages"]
        self.assertEqual(analyst_round_3[:len(second.turns[0].conversation)], second.turns[0].conversation)
        self.assertIn("Round 2 (rebuttal)", analyst_round_3[-1]["content"])


class ContextWindow(unittest.TestCase):
    def test_every_call_asks_for_the_larger_context_window(self):
        debate = Debate(PURCHASE)
        fake = FakeChat(opening_replies() + rebuttal_replies())
        run_opening_round(debate, chat=fake)
        run_rebuttal_round(debate, chat=fake)
        self.assertEqual({call["options"]["num_ctx"] for call in fake.calls}, {config.CONTEXT_TOKENS})


if __name__ == "__main__":
    unittest.main()
