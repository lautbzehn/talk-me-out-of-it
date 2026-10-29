"""Phase 6 tests, milestone 1: the transcript contract, the session store, the engine snapshot and ask.py.
None of them call the real model.

Run with:  .venv/bin/python -m unittest -v
"""

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ask
import council
import scoring
import session_store
from agents.roster import COUNCIL
from session_schema import SessionError, check_session, parse_session
from tests.helpers import FakeChat
from tests.test_phase4_council import intake_reply
from tests.test_phase5_evals import COUNCIL_SESSION, DECLINED_SESSION, council_script


def fresh(session=COUNCIL_SESSION) -> dict:
    return copy.deepcopy(session)


def last_turn(session: dict, agent: str) -> dict:
    """The agent's last good turn, which scoring read."""
    turns = [turn for round_ in session["rounds"] for turn in round_["turns"] if turn["agent"] == agent and turn["status"] == "ok"]
    return turns[-1]


class Contract(unittest.TestCase):
    def test_sessions_the_engine_makes_pass(self):
        self.assertEqual(check_session(COUNCIL_SESSION), [])
        self.assertEqual(check_session(DECLINED_SESSION), [])
        self.assertEqual(COUNCIL_SESSION["schema_version"], 3)

    def test_an_older_session_without_an_engine_block_still_passes(self):
        session = fresh()
        del session["engine"]
        session["schema_version"] = 2
        self.assertEqual(check_session(session), [])

    def test_a_schema_3_council_must_carry_its_engine(self):
        session = fresh()
        del session["engine"]
        self.assertIn("engine snapshot", " ".join(check_session(session)))

    def test_unknown_extra_fields_are_fine(self):
        session = fresh()
        session["added_later"] = {"anything": 1}
        session["rounds"][0]["turns"][0]["trace"]["new_detail"] = True
        self.assertEqual(check_session(session), [])

    def test_unsupported_input_is_refused_in_plain_words(self):
        self.assertEqual(check_session("not a dict"), ["a session must be a JSON object"])
        old = fresh()
        old["schema_version"] = 1
        self.assertIn("schema_version 1 is not supported", check_session(old)[0])
        error = fresh()
        error["kind"] = "error"
        self.assertTrue(check_session(error))

    def test_a_missing_or_wrong_piece_is_named_by_where_it_is(self):
        session = fresh()
        del session["purchase"]["item"]
        session["rounds"][0]["turns"][1]["take_or_rebuttal"]["lean"] = "maybe"
        problems = check_session(session)
        self.assertTrue(any(p.startswith("purchase.item") for p in problems), problems)
        self.assertTrue(any(p.startswith("rounds.0.turns.1.take_or_rebuttal.lean") for p in problems), problems)

    def test_a_turn_must_agree_with_its_status(self):
        no_reply = fresh()
        no_reply["rounds"][0]["turns"][0]["take_or_rebuttal"] = None
        self.assertIn("has no reply", " ".join(check_session(no_reply)))
        failed_with_reply = fresh()
        failed_with_reply["rounds"][0]["turns"][0]["status"] = "failed"
        self.assertIn("failed but has a reply", " ".join(check_session(failed_with_reply)))

    def test_a_reply_has_a_take_or_a_response_not_both(self):
        session = fresh()
        session["rounds"][0]["turns"][0]["take_or_rebuttal"]["response"] = "And a response too."
        self.assertIn("either a take", " ".join(check_session(session)))

    def test_a_declined_session_has_no_debate(self):
        session = fresh(DECLINED_SESSION)
        session["rounds"] = fresh()["rounds"][:1]
        self.assertTrue(check_session(session))

    def test_formula_two_scoring_must_record_its_leans(self):
        session = fresh()
        del session["scoring"]["leans"]
        self.assertIn("must record leans", " ".join(check_session(session)))

    def test_parse_session_raises_with_the_same_problems(self):
        session = fresh()
        session["scoring"]["score"] = 7.0
        with self.assertRaises(SessionError) as caught:
            parse_session(session)
        self.assertEqual(caught.exception.problems, check_session(session))


class Story(unittest.TestCase):
    """The parts of a session have to agree. This is what stops a hand-edited verdict."""

    def test_a_changed_score_is_caught(self):
        session = fresh()
        session["scoring"]["score"] = 7.0
        self.assertIn("the score is 7.0, but its own ratings give 6.0", check_session(session))

    def test_a_changed_verdict_is_caught(self):
        # The scripted council scores 6.0, which points to Buy, but all four members lean Wait, so a rule holds it at Wait.
        session = fresh()
        self.assertEqual((session["scoring"]["score_verdict"], session["scoring"]["verdict"]), ("buy", "wait"))
        session["scoring"].update(verdict="buy", verdict_label="Buy", rail=None, rail_note=None)
        problems = " ".join(check_session(session))
        self.assertIn("give wait (rail: buy_needs_a_buy_lean)", problems)

    def test_a_wrong_label_is_caught(self):
        session = fresh()
        session["scoring"]["verdict_label"] = "Buy"
        self.assertIn("does not match the verdict", " ".join(check_session(session)))

    def test_ratings_that_are_not_the_debates_are_caught(self):
        session = fresh()
        last_turn(session, "The Analyst")["take_or_rebuttal"]["ratings"]["longevity"]["score"] = 9
        self.assertIn("scoring.inputs are not the ratings", " ".join(check_session(session)))

    def test_leans_that_are_not_the_debates_are_caught(self):
        session = fresh()
        last_turn(session, "Future You")["take_or_rebuttal"]["lean"] = "skip"
        self.assertIn("scoring.leans are not the leans", " ".join(check_session(session)))

    def test_rounds_must_be_in_order(self):
        session = fresh()
        session["rounds"][0]["number"] = 2
        self.assertIn("must count 1, 2, 3", " ".join(check_session(session)))
        session = fresh()
        session["rounds"][0]["kind"], session["rounds"][1]["kind"] = "rebuttal", "opening"
        self.assertIn("opening, then rebuttal", " ".join(check_session(session)))

    def test_a_member_speaks_once_per_round(self):
        session = fresh()
        session["rounds"][0]["turns"].append(copy.deepcopy(session["rounds"][0]["turns"][0]))
        self.assertIn("speaks more than once", " ".join(check_session(session)))

    def test_a_verdict_needs_two_members(self):
        session = fresh()
        for round_ in session["rounds"]:
            round_["turns"] = round_["turns"][:1]
        self.assertIn("needs at least two", " ".join(check_session(session)))

    def test_an_older_formula_is_checked_for_shape_but_not_recomputed(self):
        session = fresh()
        session["scoring"].update(formula_version=1, score=7.9, verdict="buy", verdict_label="Buy")
        for key in ("leans", "score_verdict", "rail", "rail_note"):
            del session["scoring"][key]
        self.assertEqual(check_session(session), [])  # 7.9 would not recompute under today's rules
        last_turn(session, "The Analyst")["take_or_rebuttal"]["ratings"]["longevity"]["score"] = 9
        self.assertTrue(check_session(session))  # but its ratings must still be the debate's

    def test_every_real_verdict_in_the_scripted_runs_rechecks(self):
        # A council with a Buy lean, and one with a Skip lean, built by editing the scripted one the way the engine would.
        for lean, score_value, expected in (("buy", 8, "buy"), ("skip", 2, "skip")):
            with self.subTest(lean=lean):
                session = fresh()
                for round_ in session["rounds"]:
                    for turn in round_["turns"]:
                        for rating in turn["take_or_rebuttal"]["ratings"].values():
                            rating["score"] = score_value
                last_turn(session, "The Analyst")["take_or_rebuttal"]["lean"] = lean
                inputs = {a: {n: r["score"] for n, r in last_turn(session, a)["take_or_rebuttal"]["ratings"].items()}
                          for a in session["scoring"]["inputs"]}
                result = {**session["scoring"], "inputs": inputs, "score": scoring.average_of(inputs),
                          "verdict": expected, "verdict_label": scoring.VERDICT_LABELS[expected],
                          "score_verdict": expected, "rail": None, "rail_note": None,
                          "leans": {a: last_turn(session, a)["take_or_rebuttal"]["lean"] for a in inputs}}
                session["scoring"] = result
                self.assertEqual(check_session(session), [])


class AverageOf(unittest.TestCase):
    def test_it_gives_the_same_score_as_score(self):
        from agents.schemas import AgentTake  # noqa: F401 (the replies come from the scripted session)
        self.assertEqual(scoring.average_of(COUNCIL_SESSION["scoring"]["inputs"]), COUNCIL_SESSION["scoring"]["score"])

    def test_cost_of_waiting_is_left_out(self):
        inputs = {"Budget Guardian": {"price_for_the_problem": 6, "cost_of_waiting": 1, "better_than_keeping_it": 4}}
        self.assertEqual(scoring.average_of(inputs), 5.0)
        self.assertEqual(scoring.counted_ratings(inputs), {"Budget Guardian": [(6, 1), (4, 1)]})

    def test_a_rating_with_no_weight_or_nothing_to_score_is_an_error(self):
        with self.assertRaises(ValueError):
            scoring.average_of({"X": {"made_up_rating": 5}})
        with self.assertRaises(ValueError):
            scoring.average_of({})


class EngineSnapshot(unittest.TestCase):
    def setUp(self):
        self.engine = council.engine_snapshot()

    def test_it_describes_every_council_member(self):
        self.assertEqual([a["name"] for a in self.engine["agents"]], [agent.name for agent in COUNCIL])
        for card, agent in zip(self.engine["agents"], COUNCIL):
            self.assertEqual(card["system_prompt"], agent.system_prompt())
            self.assertEqual((card["focus"], card["voice"]), (agent.focus, agent.voice))
            self.assertEqual(list(card["rubric"]), list(agent.ratings.model_fields))
            self.assertEqual(card["required_tools"], list(agent.required_tools))

    def test_it_carries_the_tools_prompts_and_scoring_rules(self):
        self.assertEqual(set(self.engine["tools"]), {"cost_per_use", "estimate_resale"})
        self.assertEqual(set(self.engine["prompts"]), {"intake", "judge", "rebuttal"})
        rules = self.engine["rules"]["scoring"]
        self.assertEqual((rules["buy_at"], rules["wait_at"], rules["formula_version"]), (5.5, 4.5, scoring.FORMULA_VERSION))
        self.assertEqual(rules["weights"], scoring.WEIGHTS)

    def test_it_is_plain_data_and_the_session_carries_it(self):
        self.assertEqual(json.loads(json.dumps(self.engine)), self.engine)
        self.assertEqual(COUNCIL_SESSION["engine"], self.engine)

    def test_a_declined_session_does_not_carry_it(self):
        self.assertNotIn("engine", DECLINED_SESSION)


class SessionFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / "sessions"

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_then_load_gives_the_same_session(self):
        path = session_store.save_session(COUNCIL_SESSION, self.folder)
        self.assertEqual(path.parent, self.folder)
        self.assertEqual(session_store.load_session(path), COUNCIL_SESSION)
        self.assertTrue(path.read_text().endswith("}\n"))

    def test_the_file_is_named_from_when_it_started_and_what_it_was_about(self):
        session = fresh()
        session["created_at"] = "2026-10-28T23:49:29+00:00"
        self.assertEqual(session_store.session_id(session), "20261028-234929-headphones")
        session["created_at"] = "2026-10-29T01:49:29+02:00"  # the same moment, written with another offset
        self.assertEqual(session_store.session_id(session), "20261028-234929-headphones")

    def test_saving_the_same_session_twice_makes_one_file(self):
        session_store.save_session(COUNCIL_SESSION, self.folder)
        session_store.save_session(COUNCIL_SESSION, self.folder)
        self.assertEqual(len(list(self.folder.iterdir())), 1)

    def test_no_temporary_file_is_left_behind(self):
        session_store.save_session(COUNCIL_SESSION, self.folder)
        self.assertEqual([p.suffix for p in self.folder.iterdir()], [".json"])

    def test_a_session_that_breaks_the_contract_is_not_written(self):
        session = fresh()
        session["scoring"]["score"] = 7.0
        with self.assertRaises(SessionError):
            session_store.save_session(session, self.folder)
        self.assertFalse(self.folder.exists())

    def test_a_failed_write_leaves_the_old_file_whole(self):
        path = session_store.save_session(COUNCIL_SESSION, self.folder)
        before = path.read_text()
        changed = fresh()
        changed["judge"]["ruling"] = "A different ruling for the same session."
        with mock.patch("session_store.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                session_store.save_session(changed, self.folder)
        self.assertEqual(path.read_text(), before)
        self.assertEqual(session_store.load_session(path), COUNCIL_SESSION)

    def test_text_that_is_not_ascii_is_kept_readable(self):
        session = fresh()
        session["purchase"]["why"] = "My café’s old tablet died."
        path = session_store.save_session(session, self.folder)
        self.assertIn("café’s", path.read_text(encoding="utf-8"))
        self.assertEqual(session_store.load_session(path)["purchase"]["why"], "My café’s old tablet died.")

    def test_data_that_is_not_json_is_refused(self):
        session = fresh()
        session["timing"]["when"] = {1, 2}  # a set is not JSON
        with self.assertRaises(SessionError) as caught:
            session_store.save_session(session, self.folder)
        self.assertIn("not plain JSON", str(caught.exception))

    def test_loading_says_what_is_wrong(self):
        with self.assertRaises(SessionError) as caught:
            session_store.load_session(self.folder / "nothing.json")
        self.assertIn("does not exist", str(caught.exception))
        self.folder.mkdir()
        (self.folder / "broken.json").write_text("{not json")
        with self.assertRaises(SessionError) as caught:
            session_store.load_session(self.folder / "broken.json")
        self.assertIn("not valid JSON", str(caught.exception))
        bad = fresh()
        bad["scoring"]["score"] = 7.0
        (self.folder / "tampered.json").write_text(json.dumps(bad))
        with self.assertRaises(SessionError) as caught:
            session_store.load_session(self.folder / "tampered.json")
        self.assertIn("its own ratings give 6.0", str(caught.exception))

    def test_slugs(self):
        self.assertEqual(session_store.slug("Noise-cancelling headphones"), "noise-cancelling-headphones")
        self.assertEqual(session_store.slug("  PS5 Pro!! (2024)  "), "ps5-pro-2024")
        self.assertEqual(session_store.slug("???"), "session")
        self.assertLessEqual(len(session_store.slug("a" * 200)), 40)


class Listing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_summaries_come_newest_first_and_a_bad_file_does_not_hide_the_rest(self):
        older, newer = fresh(), fresh(DECLINED_SESSION)
        older["created_at"] = "2026-10-28T10:00:00+00:00"
        newer["created_at"] = "2026-10-28T12:00:00+00:00"
        session_store.save_session(older, self.folder)
        session_store.save_session(newer, self.folder)
        (self.folder / "broken.json").write_text("{nope")
        entries = session_store.list_sessions(self.folder)

        self.assertEqual([e.get("kind") for e in entries], ["declined", "council", None])
        self.assertIn("not valid JSON", entries[2]["problems"][0])
        council_entry = entries[1]
        self.assertEqual((council_entry["item"], council_entry["verdict"], council_entry["score"]), ("Headphones", "wait", 6.0))
        self.assertEqual(council_entry["rail"], "buy_needs_a_buy_lean")
        self.assertIsNone(entries[0]["verdict"])  # a decline has no verdict

    def test_an_empty_or_missing_folder_lists_nothing(self):
        self.assertEqual(session_store.list_sessions(self.folder), [])
        self.assertEqual(session_store.list_sessions(self.folder / "not-there"), [])

    def test_the_check_command_reports_and_sets_its_exit_code(self):
        session_store.save_session(COUNCIL_SESSION, self.folder)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = session_store.main([str(self.folder)])
        self.assertEqual(code, 0)
        self.assertIn("OK   ", out.getvalue())
        self.assertIn("held by a rule", out.getvalue())
        self.assertIn("1 fine, 0 with problems", out.getvalue())

        (self.folder / "broken.json").write_text("{nope")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = session_store.main([str(self.folder)])
        self.assertEqual(code, 1)
        self.assertIn("BAD  broken.json", out.getvalue())


class Ask(unittest.TestCase):
    ARGS = ["Noise-cancelling headphones", "--price", "350", "--want", "7",
            "--why", "I commute on a loud train.", "--owns", "Cheap wired earbuds"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_ask(self, args, chat):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ask.main([*args, "--folder", str(self.folder)], chat=chat)
        return code, out.getvalue(), err.getvalue()

    def test_a_council_runs_prints_the_verdict_and_saves_a_valid_transcript(self):
        code, out, _ = self.run_ask(self.ARGS, FakeChat(council_script()))
        self.assertEqual(code, 0)
        self.assertIn("VERDICT: WAIT 30 DAYS", out)
        self.assertIn("no member leaned Buy", out)  # the code-written note for the rule that held the verdict
        self.assertIn(ask.DISCLAIMER, out)
        [path] = list(self.folder.glob("*.json"))
        self.assertEqual(session_store.load_session(path)["purchase"]["current_device"], "Cheap wired earbuds")

    def test_something_that_is_not_a_gadget_is_declined_and_saved(self):
        code, out, _ = self.run_ask(["Leather sofa", "--price", "1200", "--want", "6", "--why", "My old couch sags."],
                                    FakeChat([intake_reply(gadget=False)]))
        self.assertEqual(code, 0)
        self.assertIn("only weighs in on tech gadgets", out)
        [path] = list(self.folder.glob("*.json"))
        self.assertEqual(session_store.load_session(path)["kind"], "declined")

    def test_a_bad_purchase_is_refused_before_anything_runs(self):
        chat = FakeChat([])
        code, out, err = self.run_ask(["Laptop", "--price", "-5", "--want", "11", "--why", "x"], chat)
        self.assertEqual((code, out, chat.calls, list(self.folder.glob("*.json"))), (2, "", [], []))
        for problem in ("price", "want_level", "why"):
            self.assertIn(problem, err)

    def test_the_item_and_flags_become_the_purchase(self):
        args = mock.Mock(item="Sequel", price=70.0, why="Fan.", want=10, owns=None)
        purchase = ask.build_purchase(args)
        self.assertEqual((purchase.item, purchase.price, purchase.want_level, purchase.current_device), ("Sequel", 70.0, 10, None))

    def test_ollama_not_running_is_a_plain_message_not_a_crash(self):
        def down(**kwargs):
            raise ConnectionError("refused")
        code, _, err = self.run_ask(self.ARGS, down)
        self.assertEqual(code, 1)
        self.assertIn("brew services start ollama", err)
        self.assertEqual(list(self.folder.glob("*.json")), [])


class Demos(unittest.TestCase):
    def test_the_demos_still_import_after_the_display_code_moved(self):
        import demo_phase3
        import demo_phase4
        self.assertIs(demo_phase3.ProgressChat, __import__("display").ProgressChat)
        self.assertIs(demo_phase4.on_event, __import__("display").on_event)


if __name__ == "__main__":
    unittest.main()
