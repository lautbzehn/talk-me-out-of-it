"""Phase 2 tests. None of them call the real model, so they finish in well under a second.

Run with:  .venv/bin/python -m unittest -v
"""

import json
import unittest

from pydantic import ValidationError

from agents.analyst import ANALYST
from agents.base import StructuredOutputError, call_structured
from agents.schemas import AgentTake, AnalystRatings, Purchase
from tests.helpers import FakeChat

AnalystTake = AgentTake[AnalystRatings]


def valid_take(**changes) -> dict:
    """A correct Analyst reply. Tests pass `changes` to break one piece of it."""
    data = {
        "take": "At this price you pay well under a dollar per commute. The jump from cheap earbuds is huge.",
        "ratings": {
            "value_per_use": {"reason": "Used twice a day on the train.", "score": 8},
            "longevity": {"reason": "Good headphones last several years.", "score": 7},
            "upgrade_gap": {"reason": "Cheap earbuds block almost no noise.", "score": 9},
        },
        "lean": "buy",
        "confidence": 7,
    }
    data.update(changes)
    return data


class SchemaRules(unittest.TestCase):
    def test_valid_reply_passes(self):
        take = AnalystTake.model_validate(valid_take())
        self.assertEqual(take.ratings.upgrade_gap.score, 9)

    def test_score_above_10_is_rejected(self):
        bad = valid_take()
        bad["ratings"]["longevity"]["score"] = 11
        with self.assertRaises(ValidationError):
            AnalystTake.model_validate(bad)

    def test_reason_that_starts_with_a_score_is_rejected(self):
        for leaked in ["8/10 - lasts a long time.", "9 = used every day.", "7: solid build.", "6 - fine."]:
            with self.subTest(reason=leaked):
                bad = valid_take()
                bad["ratings"]["longevity"]["reason"] = leaked
                with self.assertRaises(ValidationError):
                    AnalystTake.model_validate(bad)

    def test_reason_that_starts_with_a_real_number_is_allowed(self):
        for fine in ["3-5 years is typical for headphones.", "90 minutes a day is heavy use."]:
            with self.subTest(reason=fine):
                ok = valid_take()
                ok["ratings"]["longevity"]["reason"] = fine
                AnalystTake.model_validate(ok)

    def test_unknown_lean_is_rejected(self):
        with self.assertRaises(ValidationError):
            AnalystTake.model_validate(valid_take(lean="maybe"))

    def test_missing_rubric_item_is_rejected(self):
        bad = valid_take()
        del bad["ratings"]["upgrade_gap"]
        with self.assertRaises(ValidationError):
            AnalystTake.model_validate(bad)

    def test_purchase_rejects_want_level_out_of_range(self):
        with self.assertRaises(ValidationError):
            Purchase(item="Headphones", price=350, why="Loud train", want_level=15)

    def test_prompt_lists_every_rubric_item(self):
        for name in AnalystRatings.model_fields:
            self.assertIn(name, ANALYST.system_prompt())


class RetryLoop(unittest.TestCase):
    def test_recovers_from_malformed_json(self):
        fake = FakeChat(["this is not json at all", json.dumps(valid_take())])
        take, attempts = call_structured("system", "user", AnalystTake, chat=fake)

        self.assertEqual(take.lean, "buy")
        self.assertEqual([a["ok"] for a in attempts], [False, True])
        # The second call must show the model its bad reply and what was wrong with it.
        retry_messages = fake.calls[1]["messages"]
        self.assertEqual(retry_messages[-2], {"role": "assistant", "content": "this is not json at all"})
        self.assertIn("broke these rules", retry_messages[-1]["content"])

    def test_recovers_from_out_of_range_score(self):
        bad = valid_take()
        bad["ratings"]["value_per_use"]["score"] = 0
        fake = FakeChat([json.dumps(bad), json.dumps(valid_take())])
        take, attempts = call_structured("system", "user", AnalystTake, chat=fake)

        self.assertEqual(len(attempts), 2)
        self.assertIn("ratings.value_per_use.score", attempts[0]["error"])

    def test_gives_up_after_max_attempts(self):
        fake = FakeChat(["bad"] * 3)
        with self.assertRaises(StructuredOutputError) as caught:
            call_structured("system", "user", AnalystTake, chat=fake, max_attempts=3)

        self.assertEqual(len(caught.exception.attempts), 3)
        self.assertEqual(len(fake.calls), 3)

    def test_sends_schema_to_the_model(self):
        fake = FakeChat([json.dumps(valid_take())])
        call_structured("system", "user", AnalystTake, chat=fake)
        self.assertIn("ratings", fake.calls[0]["format"]["properties"])


if __name__ == "__main__":
    unittest.main()
