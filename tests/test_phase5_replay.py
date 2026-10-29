"""Phase 5 tests, step 3: the replay tool rebuilds saved sessions and reruns scoring or the Judge.
None of them call the real model.

Run with:  .venv/bin/python -m unittest -v
"""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scoring
from council import run_council
from evals import replay
from evals.run_evals import run_evals
from tests.helpers import FakeChat
from tests.test_phase4 import PURCHASE
from tests.test_phase4_council import intake_reply, judge_reply
from tests.test_phase5_evals import COUNCIL_SESSION, DECLINED_SESSION, SOFA, council_script, scenario


def always(verdict: str):
    """A stand-in formula that ignores the ratings, to show the replay uses what it is given."""
    def score(final):
        return {**scoring.score(final), "verdict": verdict, "formula_version": 99}
    return score


class Rebuild(unittest.TestCase):
    def test_the_debate_comes_back_as_it_was(self):
        debate = replay.rebuild_debate(COUNCIL_SESSION)
        self.assertEqual(debate.purchase.item, PURCHASE.item)
        self.assertEqual(debate.category, "audio")
        self.assertEqual([r.kind for r in debate.rounds], ["opening", "rebuttal"])
        first = debate.rounds[0].turns[0]
        self.assertEqual(first.agent, "The Analyst")
        self.assertEqual(first.reply.lean, "buy")
        self.assertTrue(first.trace["tool_calls"])  # the Judge's digest reads tool results from here

    def test_rescoring_with_the_same_formula_gives_the_same_result(self):
        self.assertEqual(replay.rescore(COUNCIL_SESSION), COUNCIL_SESSION["scoring"])

    def test_the_opening_round_alone(self):
        # Every opening rating in the script is 5, every rebuttal rating 6.
        self.assertEqual(replay.rescore(COUNCIL_SESSION, rounds=1)["score"], 5.0)
        self.assertEqual(replay.rescore(COUNCIL_SESSION)["score"], 6.0)

    def test_any_formula_can_be_passed_in(self):
        self.assertEqual(replay.rescore(COUNCIL_SESSION, score=always("skip"))["verdict"], "skip")

    def test_a_declined_session_has_no_debate(self):
        with self.assertRaises(ValueError):
            replay.rebuild_debate(DECLINED_SESSION)
        self.assertIs(replay.replayed(DECLINED_SESSION), DECLINED_SESSION)

    def test_a_renamed_rubric_key_still_fits(self):
        session = copy.deepcopy(COUNCIL_SESSION)
        for round_ in session["rounds"]:
            for turn in round_["turns"]:
                if turn["agent"] == "The Analyst":
                    ratings = turn["take_or_rebuttal"]["ratings"]
                    ratings["old_value_name"] = ratings.pop("value_per_use")
        with self.assertRaises(Exception):
            replay.rebuild_debate(session)
        with mock.patch.dict(replay.RENAMED_KEYS, {"old_value_name": "value_per_use"}):
            self.assertEqual(replay.rescore(session), COUNCIL_SESSION["scoring"])

    def test_the_saved_session_is_never_changed(self):
        session = copy.deepcopy(COUNCIL_SESSION)
        replay.replayed(session, score=always("buy"))
        self.assertEqual(session, COUNCIL_SESSION)


class Rejudge(unittest.TestCase):
    def test_the_judge_reruns_on_the_saved_debate(self):
        fake = FakeChat([judge_reply(ruling="A month will show whether the commute still bothers you.")])
        again = replay.replayed(COUNCIL_SESSION, with_judge=True, chat=fake)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(again["judge"]["ruling"], "A month will show whether the commute still bothers you.")
        self.assertFalse(again["judge"]["fallback_used"])
        prompt = fake.calls[0]["messages"][-1]["content"]
        self.assertIn("Final leans: 4 WAIT", prompt)  # it read the rebuilt debate

    def test_without_judge_no_model_is_called(self):
        replay.replayed(COUNCIL_SESSION, chat=FakeChat([]))  # an empty script would fail on any call


class ReplayRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / "run"
        scenarios = [scenario("wait"), scenario("declined", category=None, id="sofa")]
        scenarios[1] = scenarios[1].model_copy(update={"purchase": scenarios[1].purchase.model_validate(SOFA)})
        run_evals(scenarios, self.folder, "v1.0", chat=FakeChat([*council_script(), intake_reply(gadget=False)]),
                  say=lambda line: None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_formula_same_rows(self):
        result = replay.replay_run(self.folder)
        self.assertEqual(result["stored"], result["replayed"])
        self.assertEqual(result["opening"], {"headphones-r1": "wait"})

    def test_a_new_formula_shows_up_in_the_comparison(self):
        result = replay.replay_run(self.folder, score=always("buy"))
        self.assertEqual(result["formula_version"], 99)
        text = replay.render_comparison(result)
        self.assertIn("stored 2 of 2 (100%), replayed 1 of 2 (50%)", text)
        self.assertIn("| headphones | Wait | Wait 6.0 | Buy 6.0 (**no**) | Buy |", text)
        self.assertIn("changed the verdict in 0 of 1 councils", text)
        self.assertNotIn("—", text)

    def test_save_writes_next_to_the_run_and_leaves_sessions_alone(self):
        before = (self.folder / "sessions" / "headphones-r1.json").read_text()
        with mock.patch("builtins.print"):
            replay.main([str(self.folder), "--save"])
        self.assertTrue((self.folder / "replay.md").exists())
        saved = json.loads((self.folder / "replay.json").read_text())
        self.assertEqual(saved["formula_version"], scoring.FORMULA_VERSION)
        self.assertEqual((self.folder / "sessions" / "headphones-r1.json").read_text(), before)


if __name__ == "__main__":
    unittest.main()
