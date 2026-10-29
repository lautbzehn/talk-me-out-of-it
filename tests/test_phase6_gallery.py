"""Phase 6 tests, milestone 2: the gallery pool, the batch generator, the review, and promote/remove/index.
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

import gallery
import generate
import session_store
from council import CouncilError
from evals.scenarios import load_scenarios
from gallery import Pool, PoolEntry
from session_schema import SessionError
from tests.helpers import FakeChat
from tests.test_phase4 import PURCHASE
from tests.test_phase4_council import intake_reply
from tests.test_phase5_evals import COUNCIL_SESSION, DECLINED_SESSION, SOFA, council_script


def clean_council(verdict_fields: dict | None = None, created_at: str | None = None) -> dict:
    """The scripted council with Future You's opening in its proper voice, so nothing in it should be flagged."""
    session = copy.deepcopy(COUNCIL_SESSION)
    for turn in session["rounds"][0]["turns"]:
        if turn["agent"] == "Future You":
            turn["take_or_rebuttal"]["take"] = "Six months later, I still reach for them on the train. They earned their place."
    if created_at:
        session["created_at"] = created_at
    return session


def pool_with(*entries: PoolEntry) -> Pool:
    return Pool(version="v1.0", date="10.28.2026", about="A test pool.", purchases=list(entries))


HEADPHONES = PoolEntry(id="headphones", why_featured="The scripted test purchase.", purchase=PURCHASE)
SOFA_ENTRY = PoolEntry(id="leather-sofa", why_featured="Not a gadget: the polite decline.", purchase=SOFA)


class ThePool(unittest.TestCase):
    def test_the_real_pool_loads_and_matches_the_eval_scenarios(self):
        pool = gallery.load_pool()
        self.assertEqual(len(pool.purchases), 13)
        scenarios = {s.id: s for s in load_scenarios().scenarios}
        for entry in pool.purchases:
            if entry.id in scenarios:
                self.assertEqual(entry.purchase, scenarios[entry.id].purchase, entry.id)
        self.assertEqual([e.id for e in pool.purchases if e.id not in scenarios], ["leather-sofa"])
        self.assertIn("injection-gaming-laptop", [e.id for e in pool.purchases])

    def test_a_typo_in_a_purchase_is_an_error(self):
        with self.assertRaises(ValueError):
            PoolEntry(id="x-y", why_featured="A typo test entry.", purchase={**PURCHASE.model_dump(), "current_devise": "x"})

    def test_ids_are_unique_and_well_formed(self):
        with self.assertRaises(ValueError):
            pool_with(HEADPHONES, HEADPHONES)
        with self.assertRaises(ValueError):
            PoolEntry(id="Has Spaces", why_featured="A bad id test entry.", purchase=PURCHASE)


class Review(unittest.TestCase):
    def test_a_clean_council_has_no_flags_and_notes_its_rule(self):
        entry = gallery.review(clean_council())
        self.assertEqual(entry["flags"], [])
        self.assertTrue(entry["clean"])
        self.assertTrue(any("a rule held the verdict" in note for note in entry["notes"]))

    def test_the_judge_naming_the_verdict_it_already_gave_is_flagged(self):
        session = clean_council()  # its verdict is Wait 30 days
        session["judge"]["would_change_verdict"] = "If the commute got longer, the verdict might change to Wait."
        self.assertTrue(any("the verdict it already gave" in flag for flag in gallery.review(session)["flags"]))
        session["judge"]["would_change_verdict"] = "Using them every day would turn this into a Buy."
        self.assertEqual(gallery.review(session)["flags"], [])

    def test_false_claims_about_who_leaned_where_are_flagged(self):
        wait_two = {"The Analyst": "buy", "Future You": "buy", "Budget Guardian": "wait", "Alternatives Hunter": "wait"}
        one_buy = {"The Analyst": "buy", "Future You": "wait", "Budget Guardian": "wait", "Alternatives Hunter": "wait"}
        all_wait = dict.fromkeys(wait_two, "wait")
        wait_skip = {"The Analyst": "wait", "Future You": "wait", "Budget Guardian": "wait", "Alternatives Hunter": "skip"}
        false_claims = [  # sentences from real Judge summaries, with the leans that contradict them
            ("The verdict is Buy, even though no member leaned Wait 30 days.", wait_two),
            ("The score led to a Buy verdict, but no member explicitly leaned Buy.", one_buy),
            ("The verdict is Buy, despite no clear lean towards Buy or Skip from the council members.", one_buy),
            ("None of the members leaned toward Skip.", wait_skip),
            ("This led to a unanimous lean of 'Wait'.", wait_skip),
            ("All four members leaned Wait.", wait_skip),
        ]
        for text, leans in false_claims:
            with self.subTest(text=text):
                self.assertTrue(gallery.false_lean_claims(text, leans), text)
        true_claims = [
            ("The score points to Buy, but no member leaned Buy, so the verdict holds at Wait 30 days.", all_wait),
            ("The verdict is Skip, as no member leaned Buy and the score fell below the threshold.", wait_skip),
            ("The Analyst and Future You leaning BUY, while the others leaned WAIT.", wait_two),
            ("The council showed a unanimous lean of Wait.", all_wait),
            ("All four members leaned Wait.", all_wait),
            ("No member leaned Skip.", one_buy),
            ("There was no clear majority lean towards Buy or Wait.", {"a": "buy", "b": "buy", "c": "wait", "d": "wait"}),
        ]
        for text, leans in true_claims:
            with self.subTest(text=text):
                self.assertEqual(gallery.false_lean_claims(text, leans), [], text)

    def test_a_false_lean_claim_in_the_judge_text_flags_the_session(self):
        session = clean_council()  # all four members end on Wait
        session["judge"]["summary"] = "The council split. The verdict is Wait 30 days even though no member leaned Wait."
        flags = gallery.review(session)["flags"]
        self.assertTrue(any("the Judge's summary claims" in flag and "4 wait" in flag for flag in flags), flags)

    def test_a_template_ruling_is_flagged(self):
        session = clean_council()
        session["judge"]["fallback_used"] = True
        self.assertIn("the ruling is the code template, not the Judge's own", gallery.review(session)["flags"])

    def test_a_session_without_its_engine_block_is_flagged(self):
        session = clean_council()
        del session["engine"]
        session["schema_version"] = 2
        self.assertTrue(any("no engine snapshot" in flag for flag in gallery.review(session)["flags"]))

    def test_broken_text_and_voice_slips_are_flagged(self):
        session = clean_council()
        turn = session["rounds"][0]["turns"][0]
        turn["take_or_rebuttal"]["ratings"]["longevity"]["reason"] = "It should last a good while, but the battery " + "x" * 160
        turn["take_or_rebuttal"]["take"] = "This helps my daily commute a lot. It is worth a look."
        flags = " | ".join(gallery.review(session)["flags"])
        self.assertIn("cut off at its 200-character limit", flags)
        self.assertIn("may speak as the user", flags)
        session["rounds"][0]["turns"][1]["take_or_rebuttal"]["take"] = "Six months later, the picture质量 is fine. I like it."
        self.assertIn("Chinese characters", " | ".join(gallery.review(session)["flags"]))

    def test_good_moments_are_noted(self):
        session = clean_council()
        session["guard"]["triggered"] = True
        session["rounds"][1]["turns"][0]["changes"]["changed_mind"] = True
        notes = " | ".join(gallery.review(session)["notes"])
        self.assertIn("injection guard", notes)
        self.assertIn("changed their lean: The Analyst", notes)

    def test_a_decline_is_clean(self):
        entry = gallery.review(DECLINED_SESSION)
        self.assertEqual((entry["kind"], entry["flags"], entry["clean"]), ("declined", [], True))

    def test_a_folder_is_reviewed_in_pool_order_and_a_bad_file_is_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            session_store.save_session(copy.deepcopy(DECLINED_SESSION), folder)
            session_store.save_session(clean_council(), folder)
            (folder / "broken.json").write_text("{nope")
            entries = gallery.review_folder(folder, pool_with(HEADPHONES, SOFA_ENTRY))
            self.assertEqual([e.get("pool_id") for e in entries], ["headphones", "leather-sofa", None])
            self.assertIn("not valid JSON", entries[2]["problems"][0])
            text = gallery.render_review(entries)
            self.assertIn("CLEAN  Headphones", text)
            self.assertIn("BAD    broken.json", text)
            self.assertIn("3 session(s): Buy 0, Wait 1, Skip 0, declined 1; 2 clean", text)


class GalleryFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.candidates = self.root / "candidates"
        self.gallery = self.root / "gallery"
        self.council_file = session_store.save_session(clean_council(), self.candidates)
        self.decline_file = session_store.save_session(copy.deepcopy(DECLINED_SESSION), self.candidates)
        self.pool = pool_with(HEADPHONES, SOFA_ENTRY)

    def tearDown(self):
        self.tmp.cleanup()

    def index(self) -> dict:
        return json.loads((self.gallery / session_store.INDEX_NAME).read_text())

    def test_promote_copies_and_writes_the_index(self):
        saved = gallery.promote([self.decline_file, self.council_file], self.gallery, self.pool)
        self.assertEqual(sorted(p.name for p in saved), sorted([self.council_file.name, self.decline_file.name]))
        index = self.index()
        self.assertEqual(index["count"], 2)
        self.assertEqual([s["kind"] for s in index["sessions"]], ["council", "declined"])  # verdicts first, declines last
        self.assertEqual([s["pool_id"] for s in index["sessions"]], ["headphones", "leather-sofa"])
        self.assertEqual(index["sessions"][1]["why_featured"], "Not a gadget: the polite decline.")
        self.assertEqual(session_store.load_session(self.gallery / self.council_file.name), clean_council())

    def test_a_note_per_session_is_saved_in_the_gallery_copy_and_used_by_the_index(self):
        notes = ["The scripted council, held at Wait by a rule.", "Not a gadget: the polite decline, in one line."]
        gallery.promote([self.council_file, self.decline_file], self.gallery, self.pool, why=notes)
        index = self.index()
        self.assertEqual([s["why_featured"] for s in index["sessions"]], notes)
        saved = session_store.load_session(self.gallery / self.council_file.name)
        self.assertEqual(saved["gallery"], {"why_featured": notes[0]})
        self.assertNotIn("gallery", session_store.load_session(self.council_file))  # the candidate is untouched
        gallery.write_index(self.gallery, self.pool)  # rebuilding keeps the note: it lives in the transcript
        self.assertEqual([s["why_featured"] for s in self.index()["sessions"]], notes)

    def test_without_a_note_the_index_falls_back_to_the_pools_line(self):
        gallery.promote([self.decline_file], self.gallery, self.pool)
        self.assertEqual(self.index()["sessions"][0]["why_featured"], "Not a gadget: the polite decline.")

    def test_the_number_of_notes_must_match_the_number_of_files(self):
        with self.assertRaises(SessionError) as caught:
            gallery.promote([self.council_file, self.decline_file], self.gallery, self.pool, why=["Only one note given here."])
        self.assertIn("one for each file", str(caught.exception))
        self.assertFalse(self.gallery.exists())

    def test_a_note_too_short_to_mean_anything_is_refused_and_nothing_is_copied(self):
        with self.assertRaises(SessionError):
            gallery.promote([self.council_file], self.gallery, self.pool, why=["Short"])
        self.assertFalse(self.gallery.exists())

    def test_the_command_line_takes_a_note_per_file(self):
        pool_file = self.root / "pool.json"
        pool_file.write_text(self.pool.model_dump_json())
        with contextlib.redirect_stdout(io.StringIO()):
            code = gallery.main(["--gallery", str(self.gallery), "--pool", str(pool_file), "promote",
                                 str(self.council_file), "--why", "A note written on the command line."])
        self.assertEqual(code, 0)
        self.assertEqual(self.index()["sessions"][0]["why_featured"], "A note written on the command line.")

    def test_the_index_is_never_mistaken_for_a_session(self):
        gallery.promote([self.council_file], self.gallery, self.pool)
        entries = session_store.list_sessions(self.gallery)
        self.assertEqual([e.get("problems") for e in entries], [None])

    def test_a_session_without_its_engine_block_cannot_be_promoted(self):
        old = clean_council()
        del old["engine"]
        old["schema_version"] = 2
        old_file = session_store.save_session(old, self.root / "old")
        with self.assertRaises(SessionError) as caught:
            gallery.promote([self.council_file, old_file], self.gallery, self.pool)
        self.assertIn("needs schema 3", str(caught.exception))
        self.assertFalse(self.gallery.exists())  # nothing was copied, not even the good one

    def test_a_bad_file_in_the_list_changes_nothing(self):
        broken = self.root / "broken.json"
        broken.write_text("{nope")
        with self.assertRaises(SessionError):
            gallery.promote([self.council_file, broken], self.gallery, self.pool)
        self.assertFalse(self.gallery.exists())

    def test_promoting_twice_keeps_one_copy(self):
        gallery.promote([self.council_file], self.gallery, self.pool)
        gallery.promote([self.council_file], self.gallery, self.pool)
        self.assertEqual(self.index()["count"], 1)

    def test_remove_takes_a_session_out_and_rewrites_the_index(self):
        gallery.promote([self.council_file, self.decline_file], self.gallery, self.pool)
        gallery.remove([self.decline_file.stem], self.gallery, self.pool)
        self.assertEqual([s["kind"] for s in self.index()["sessions"]], ["council"])
        self.assertTrue(self.decline_file.exists())  # the candidate stays where it was

    def test_removing_an_unknown_id_removes_nothing(self):
        gallery.promote([self.council_file, self.decline_file], self.gallery, self.pool)
        with self.assertRaises(SessionError):
            gallery.remove([self.decline_file.stem, "not-a-session"], self.gallery, self.pool)
        self.assertTrue((self.gallery / self.decline_file.name).exists())  # checked before anything was deleted
        self.assertEqual(self.index()["count"], 2)

    def test_the_index_is_the_same_file_when_nothing_changed(self):
        gallery.promote([self.council_file, self.decline_file], self.gallery, self.pool)
        first = (self.gallery / session_store.INDEX_NAME).read_bytes()
        gallery.write_index(self.gallery, self.pool)
        self.assertEqual((self.gallery / session_store.INDEX_NAME).read_bytes(), first)

    def test_a_bad_gallery_file_stops_the_index(self):
        gallery.promote([self.council_file], self.gallery, self.pool)
        (self.gallery / "hand-edited.json").write_text("{nope")
        with self.assertRaises(SessionError):
            gallery.write_index(self.gallery, self.pool)

    def test_the_command_line(self):
        pool_file = self.root / "pool.json"
        pool_file.write_text(self.pool.model_dump_json())
        base = ["--gallery", str(self.gallery), "--pool", str(pool_file)]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(gallery.main([*base, "review", str(self.candidates)]), 0)
            self.assertEqual(gallery.main([*base, "promote", str(self.council_file)]), 0)
            self.assertEqual(gallery.main([*base, "index"]), 0)
        self.assertIn("CLEAN", out.getvalue())
        self.assertIn("1 session(s)", out.getvalue())
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gallery.main([*base, "remove", "not-a-session"]), 1)
        self.assertIn("Nothing changed", err.getvalue())


class Generate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / "candidates"

    def tearDown(self):
        self.tmp.cleanup()

    def test_pick_keeps_the_order_asked_for_and_names_unknown_ids(self):
        entries = [HEADPHONES, SOFA_ENTRY]
        self.assertEqual([e.id for e in generate.pick(entries, "leather-sofa,headphones")], ["leather-sofa", "headphones"])
        self.assertEqual(generate.pick(entries, None), entries)
        with self.assertRaises(SystemExit) as caught:
            generate.pick(entries, "nope")
        self.assertIn("Known: headphones, leather-sofa", str(caught.exception))

    def test_every_finished_session_is_saved(self):
        chat = FakeChat([*council_script(), intake_reply(gadget=False)])
        results = generate.generate([HEADPHONES, SOFA_ENTRY], self.folder, chat=chat, say=lambda line: None)
        self.assertEqual([r["error"] for r in results], [None, None])
        kinds = sorted(session_store.load_session(r["saved"])["kind"] for r in results)
        self.assertEqual(kinds, ["council", "declined"])

    def test_a_council_that_stops_is_reported_and_the_run_goes_on(self):
        lines = []
        with mock.patch("generate.run_council", side_effect=[CouncilError("Only 1 agent(s) gave a final answer."),
                                                              copy.deepcopy(DECLINED_SESSION)]):
            results = generate.generate([HEADPHONES, SOFA_ENTRY], self.folder, say=lines.append)
        self.assertEqual((results[0]["saved"], results[1]["error"]), (None, None))
        self.assertTrue(any("council stopped, nothing saved" in line for line in lines))
        self.assertEqual(len(list(self.folder.glob("*.json"))), 1)

    def test_the_command_runs_reviews_and_says_how_to_promote(self):
        pool_file = Path(self.tmp.name) / "pool.json"
        pool_file.write_text(pool_with(HEADPHONES, SOFA_ENTRY).model_dump_json())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = generate.main(["--pool", str(pool_file), "--out", str(self.folder), "--only", "leather-sofa"],
                                 chat=FakeChat([intake_reply(gadget=False)]))
        self.assertEqual(code, 0)
        self.assertIn("Generating 1 candidate session(s)", out.getvalue())
        self.assertIn("CLEAN  Leather sofa", out.getvalue())
        self.assertIn("python -m gallery promote", out.getvalue())

    def test_ollama_not_running_stops_with_a_plain_message(self):
        pool_file = Path(self.tmp.name) / "pool.json"
        pool_file.write_text(pool_with(HEADPHONES).model_dump_json())

        def down(**kwargs):
            raise ConnectionError("refused")
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = generate.main(["--pool", str(pool_file), "--out", str(self.folder)], chat=down)
        self.assertEqual(code, 1)
        self.assertIn("brew services start ollama", err.getvalue())


if __name__ == "__main__":
    unittest.main()
