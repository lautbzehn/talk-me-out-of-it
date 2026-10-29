"""Phase 5 tests, step 1: the eval scenario list loads, and mistakes in it are caught.
None of them call the real model.

Run with:  .venv/bin/python -m unittest -v
"""

import copy
import unittest

from pydantic import ValidationError

from evals.scenarios import SCENARIOS_FILE, ScenarioSet, load_scenarios

GOOD_SET = {
    "version": "v1.0",
    "date": "10.23.2026",
    "about": "Test scenarios.",
    "scenarios": [
        {
            "id": "commute-headphones",
            "expected": "buy",
            "category": "audio",
            "tags": ["daily_need"],
            "why_expected": "A real daily problem at a normal price.",
            "purchase": {"item": "Headphones", "price": 350, "why": "Loud train.", "want_level": 7},
        }
    ],
}


def changed(**fields) -> dict:
    """GOOD_SET with fields of its one scenario replaced."""
    data = copy.deepcopy(GOOD_SET)
    data["scenarios"][0].update(fields)
    return data


class TheRealFile(unittest.TestCase):
    def setUp(self):
        self.scenarios = load_scenarios().scenarios

    def test_it_loads_and_has_10_to_15_scenarios(self):
        self.assertTrue(SCENARIOS_FILE.exists())
        self.assertTrue(10 <= len(self.scenarios) <= 15)

    def test_every_outcome_is_covered(self):
        expected = [scenario.expected for scenario in self.scenarios]
        for outcome in ("buy", "wait", "skip"):
            self.assertGreaterEqual(expected.count(outcome), 3, outcome)
        self.assertIn(expected.count("declined"), (1, 2))

    def test_the_phase4_samples_are_included(self):
        """The two purchases every earlier live run used, so old and new results compare."""
        items = {scenario.purchase.item for scenario in self.scenarios}
        self.assertLessEqual({"Noise-cancelling headphones", "PlayStation 5 Pro"}, items)


class CatchesMistakes(unittest.TestCase):
    def test_the_good_set_is_valid(self):
        ScenarioSet.model_validate(GOOD_SET)

    def test_unknown_verdict_is_rejected(self):
        with self.assertRaises(ValidationError):
            ScenarioSet.model_validate(changed(expected="maybe"))

    def test_unknown_category_is_rejected(self):
        with self.assertRaises(ValidationError):
            ScenarioSet.model_validate(changed(category="kitchen"))

    def test_a_typo_in_a_purchase_field_is_rejected(self):
        purchase = dict(GOOD_SET["scenarios"][0]["purchase"], current_devise="Old earbuds")
        with self.assertRaisesRegex(ValidationError, "current_devise"):
            ScenarioSet.model_validate(changed(purchase=purchase))

    def test_an_invalid_purchase_is_rejected(self):
        purchase = dict(GOOD_SET["scenarios"][0]["purchase"], want_level=11)
        with self.assertRaises(ValidationError):
            ScenarioSet.model_validate(changed(purchase=purchase))

    def test_a_declined_scenario_has_no_category(self):
        with self.assertRaisesRegex(ValidationError, "category must be null"):
            ScenarioSet.model_validate(changed(expected="declined", category="audio"))
        ScenarioSet.model_validate(changed(expected="declined", category=None))

    def test_ids_must_be_unique(self):
        data = copy.deepcopy(GOOD_SET)
        data["scenarios"].append(copy.deepcopy(data["scenarios"][0]))
        with self.assertRaisesRegex(ValidationError, "unique: commute-headphones"):
            ScenarioSet.model_validate(data)

    def test_ids_are_safe_for_file_names(self):
        with self.assertRaises(ValidationError):
            ScenarioSet.model_validate(changed(id="Commute Headphones!"))


if __name__ == "__main__":
    unittest.main()
