"""The gallery: the curated sessions the site ships, so anyone can try the experience at no cost to run.

Making it is three steps, each a command:
1. `python -m generate` runs every purchase in the pool (sessions/gallery_pool.json) through the real
   council and saves the transcripts in a new candidates folder under sessions/scratch/ (git ignores it).
2. `python -m gallery review <folder>` reads every candidate and lists what a visitor would notice:
   a template ruling instead of the Judge's, broken or cut-off text, a member speaking as the user, the Judge
   naming the verdict it already gave as the thing that would change it. It also notes the good moments:
   a rule holding the verdict, the injection guard at work, a member changing its mind.
3. `python -m gallery promote <files>` copies the chosen transcripts into sessions/gallery/ (git keeps it) and
   rewrites sessions/gallery/index.json, the list the UI reads first. `remove <id>` takes one out again,
   and `index` rebuilds the list.

Every file is checked against the transcript contract on the way in, and a council session must carry its
engine snapshot (schema 3), because the UI's "Under the hood" view reads the agents' roles from it.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agents.schemas import Purchase
from evals.report import at_limit, attempt_records, not_english, voice_flags
from session_schema import SessionError
from session_store import GALLERY_DIR, INDEX_NAME, list_sessions, load_session, save_session, summarize, write_json_atomic

POOL_FILE = Path("sessions/gallery_pool.json")
VERDICT_ORDER = {"buy": 0, "wait": 1, "skip": 2, None: 3}  # declines (no verdict) go last


# ---------------------------------------------------------------- the pool of purchases

class PoolEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")  # lowercase words joined by dashes
    why_featured: str = Field(min_length=10)  # one line on what this session shows a visitor
    purchase: Purchase

    @field_validator("purchase", mode="before")
    @classmethod
    def no_unknown_purchase_fields(cls, value):
        """Purchase ignores fields it does not know, so a typo would quietly drop an input. Here it is an error."""
        if isinstance(value, dict):
            unknown = set(value) - set(Purchase.model_fields)
            if unknown:
                raise ValueError(f"unknown purchase field(s): {', '.join(sorted(unknown))}")
        return value


class Pool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(pattern=r"^v\d+\.\d+$")
    date: str = Field(pattern=r"^\d{2}\.\d{2}\.\d{4}$")
    about: str
    purchases: list[PoolEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_are_unique(self):
        ids = [entry.id for entry in self.purchases]
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        if repeated:
            raise ValueError(f"pool ids must be unique: {', '.join(repeated)}")
        return self


def load_pool(path: Path = POOL_FILE) -> Pool:
    """Read and check the pool. A typo fails here in a second, not an hour into a generation run."""
    return Pool.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def pool_entry_for(session: dict, pool: Pool | None) -> PoolEntry | None:
    """The pool purchase this session ran, matched on the purchase itself."""
    if pool is None:
        return None
    typed = Purchase.model_validate(session["purchase"]).model_dump()
    return next((entry for entry in pool.purchases if entry.purchase.model_dump() == typed), None)


# ---------------------------------------------------------------- review

# "...the verdict might change to Buy." under a Buy. The Judge's "what would change it" should point elsewhere.
CHANGE_TO = re.compile(
    r"\b(?:change|turn|move|shift|switch|flip)\w*\b[^.]{0,40}?\b(?:to|into)\s+(?:an?\s+)?(buy|wait|skip)\b", re.IGNORECASE
)


# Claims about who leaned where. Code hands the Judge the exact final tally, and the Judge still sometimes gets it
# wrong: "even though no member leaned Wait" with two members leaning Wait; "no member explicitly leaned Buy" with
# the Analyst leaning Buy. Only claims that are plainly checkable are read: a negation ("no member / none of the
# members / no clear lean ... leaned toward Buy [or Skip]"), "unanimous ... Wait", and "all ... leaned Wait".
NO_LEAN_CLAIM = re.compile(
    r"\b(?:no|none|nobody|not one)\b[^.]{0,40}?\blean\w*\s+(?:towards?\s+|to\s+)?(buy|wait|skip)(?:\s*(?:,|or)\s*(buy|wait|skip))?",
    re.IGNORECASE,
)
UNANIMOUS_CLAIM = re.compile(r"\bunanimous\w*\s+(?:lean\w*\s+)?(?:of\s+|to\s+|towards?\s+)?['\"]?(buy|wait|skip)", re.IGNORECASE)
ALL_LEANED_CLAIM = re.compile(r"\ball\b[^.]{0,25}?\blean\w*\s+(?:towards?\s+|to\s+)?['\"]?(buy|wait|skip)", re.IGNORECASE)


def false_lean_claims(text: str, leans: dict[str, str]) -> list[str]:
    """Statements in `text` about the final leans that the real leans contradict."""
    actual = set(leans.values())
    tally = ", ".join(f"{list(leans.values()).count(lean)} {lean}" for lean in ("buy", "wait", "skip") if lean in actual)
    found = []
    for match in NO_LEAN_CLAIM.finditer(text):
        if re.search(r"majorit|consensus", match.group(0), re.IGNORECASE):
            continue  # "no clear majority lean" can be true of a 2-2 split; it says nothing about any one member
        if any(word and word.lower() in actual for word in match.groups()):
            found.append(f'"{match.group(0)}" but the final leans are {tally}')
    for match in (*UNANIMOUS_CLAIM.finditer(text), *ALL_LEANED_CLAIM.finditer(text)):
        if actual != {match.group(1).lower()}:
            found.append(f'"{match.group(0)}" but the final leans are {tally}')
    return found


def judge_slips(session: dict) -> list[str]:
    judge, scoring = session.get("judge"), session.get("scoring")
    if not judge or judge["fallback_used"]:
        return []
    slips = []
    targets = {match.group(1).lower() for match in CHANGE_TO.finditer(judge["would_change_verdict"])}
    if scoring["verdict"] in targets:
        slips.append(f'the Judge says what would change the verdict is a {scoring["verdict_label"]}, the verdict it already gave')
    for field in ("summary", "ruling", "would_change_verdict"):
        slips += [f"the Judge's {field} claims {claim}" for claim in false_lean_claims(judge[field], scoring.get("leans") or {})]
    return slips


def review(session: dict, path: Path | None = None, pool: Pool | None = None) -> dict:
    """What a visitor would notice in one transcript. `flags` are problems that keep it out of the gallery
    until a person has read them; `notes` are things worth knowing, often the good moments."""
    entry = summarize(session, path)
    match = pool_entry_for(session, pool)
    entry["pool_id"] = match.id if match else None
    flags, notes = [], []
    if session["kind"] == "council":
        if "engine" not in session:
            flags.append(f"no engine snapshot (schema {session['schema_version']}); regenerate it for the gallery")
        if session["judge"]["fallback_used"]:
            flags.append("the ruling is the code template, not the Judge's own")
        flags += judge_slips(session)
        flags += [f"{item['where']}: {item['issue']}" for item in voice_flags(session)]
        flags += [f"{item['where']}, {item['field']}: cut off at its {item['limit']}-character limit"
                  for item in at_limit(session) if item["cut_off"]]
        flags += [f"{item['where']}, {item['field']}: has Chinese characters" for item in not_english(session)]

        rounds = session["rounds"]
        if session["scoring"].get("rail"):
            notes.append(f"a rule held the verdict: {session['scoring']['rail_note']}")
        if session["guard"]["triggered"]:
            notes.append("the injection guard set instructions in the why aside")
        changed = [turn["agent"] for round_ in rounds for turn in round_["turns"] if (turn.get("changes") or {}).get("changed_mind")]
        if changed:
            notes.append(f"changed their lean: {', '.join(changed)}")
        if any(round_["kind"] == "tiebreak" for round_ in rounds):
            notes.append("went to a tiebreak round")
        tool_errors = sum(not call["ok"] for round_ in rounds for turn in round_["turns"] for call in turn["trace"].get("tool_calls", []))
        if tool_errors:
            notes.append(f"{tool_errors} tool call(s) were rejected and retried (visible under the hood)")
        retries = sum(not attempt["ok"] for attempt in attempt_records(session))
        judge_retries = sum(not attempt["ok"] for attempt in session["judge"]["trace"].get("attempts", []))
        if retries or judge_retries:
            notes.append(f"{retries} member answer(s) and {judge_retries} Judge answer(s) were sent back and redone")
    entry.update(flags=flags, notes=notes, clean=not flags)
    return entry


def review_folder(folder: Path, pool: Pool | None = None) -> list[dict]:
    """A review of every session file in `folder`, in the order the pool lists them (then any others)."""
    entries = []
    for path in sorted(p for p in Path(folder).glob("*.json") if p.name != INDEX_NAME):
        try:
            entries.append(review(load_session(path), path, pool))
        except SessionError as error:
            entries.append({"file": path.name, "problems": error.problems, "clean": False})
    order = {entry.id: n for n, entry in enumerate(pool.purchases)} if pool else {}
    entries.sort(key=lambda e: (order.get(e.get("pool_id"), len(order)), e.get("created_at") or ""))
    return entries


def render_review(entries: list[dict]) -> str:
    lines = []
    for entry in entries:
        if "problems" in entry:
            lines += [f"BAD    {entry['file']}", *[f"       - {problem}" for problem in entry["problems"]], ""]
            continue
        outcome = "declined" if entry["kind"] == "declined" else f"{entry['verdict_label']} {entry['score']}"
        minutes, seconds = divmod(round(entry["seconds"]), 60)
        lines.append(f"{'CLEAN ' if entry['clean'] else 'FLAGS '} {entry['item']} · ${entry['price']:,.0f} · {outcome}"
                     f" · {minutes}m {seconds:02d}s   ({entry['file']})")
        if entry.get("ruling"):
            lines.append(f"       \"{entry['ruling']}\"")
        lines += [f"       - {flag}" for flag in entry["flags"]]
        lines += [f"       · {note}" for note in entry["notes"]]
        lines.append("")
    good = [e for e in entries if "problems" not in e]
    mix = {label: sum(e.get("verdict") == verdict for e in good) for verdict, label in
           (("buy", "Buy"), ("wait", "Wait"), ("skip", "Skip"))}
    declined = sum(e["kind"] == "declined" for e in good)
    lines.append(f"{len(entries)} session(s): " + ", ".join(f"{label} {n}" for label, n in mix.items())
                 + f", declined {declined}; {sum(e['clean'] for e in entries)} clean")
    return "\n".join(lines)


# ---------------------------------------------------------------- the gallery folder

def write_index(gallery: Path = GALLERY_DIR, pool: Pool | None = None) -> dict:
    """Rewrite index.json from the sessions in the gallery: one summary each, Buy first, then Wait, Skip and
    declines. Every session is checked first, and a bad one stops the rewrite. There is no timestamp in the
    index on purpose: rebuilding an unchanged gallery gives the same file, so git only shows real changes."""
    gallery = Path(gallery)
    entries = list_sessions(gallery)
    bad = [entry for entry in entries if "problems" in entry]
    if bad:
        raise SessionError([f"{entry['file']}: {'; '.join(entry['problems'])}" for entry in bad])
    sessions = []
    for entry in entries:
        match = pool_entry_for(load_session(gallery / entry["file"]), pool)
        sessions.append({**entry, "pool_id": match.id if match else None,
                         "why_featured": entry["why_featured"] or (match.why_featured if match else None)})
    sessions.sort(key=lambda e: (VERDICT_ORDER[e["verdict"]], e["item"].lower(), e["created_at"]))
    index = {
        "about": "The curated gallery. Each file is a full council transcript; the UI reads this list first.",
        "count": len(sessions),
        "sessions": sessions,
    }
    write_json_atomic(gallery / INDEX_NAME, index)
    return index


def promote(paths: list[Path], gallery: Path = GALLERY_DIR, pool: Pool | None = None,
            why: list[str] | None = None) -> list[Path]:
    """Copy the chosen transcripts into the gallery and rewrite the index. Every file is checked before any is
    copied, so one bad file in the list changes nothing. `why` is one line per file on what that session shows a
    visitor; it is saved inside the gallery copy (a `gallery` block), so it is about this session and not just
    its purchase. Without it, the index falls back to the pool's line for the purchase. Promoting a session again
    replaces its gallery copy."""
    if why is not None and len(why) != len(paths):
        raise SessionError(f"{len(paths)} file(s) but {len(why)} --why line(s); give one for each file, or none")
    chosen = []
    for position, path in enumerate(paths):
        session = load_session(path)
        if session["kind"] == "council" and "engine" not in session:
            raise SessionError(f"{Path(path).name} has no engine snapshot (schema {session['schema_version']}); "
                               "the gallery needs schema 3 sessions, so regenerate it")
        if why is not None:
            session = {**session, "gallery": {"why_featured": why[position]}}
        chosen.append(session)
    saved = [save_session(session, gallery) for session in chosen]
    write_index(gallery, pool)
    return saved


def remove(ids: list[str], gallery: Path = GALLERY_DIR, pool: Pool | None = None) -> None:
    """Take sessions out of the gallery by id (the file name without .json) and rewrite the index. The candidate
    it was promoted from stays in sessions/scratch/. Every id is checked before any file is removed."""
    paths = [Path(gallery) / f"{session_id}.json" for session_id in ids]
    missing = [path.stem for path in paths if not path.exists()]
    if missing:
        raise SessionError(f"not in the gallery: {', '.join(missing)}")
    for path in paths:
        path.unlink()
    write_index(gallery, pool)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Review candidates and curate the gallery.")
    commands = parser.add_subparsers(dest="command", required=True)
    see = commands.add_parser("review", help="flag what a visitor would notice in a folder of candidates")
    see.add_argument("folder", type=Path)
    add = commands.add_parser("promote", help="copy chosen transcripts into the gallery")
    add.add_argument("files", type=Path, nargs="+")
    add.add_argument("--why", action="append",
                     help="what a session shows a visitor. Give every file first, then one --why per file in the same order")
    drop = commands.add_parser("remove", help="take sessions out of the gallery by id")
    drop.add_argument("ids", nargs="+")
    commands.add_parser("index", help="rebuild the gallery's index.json")
    parser.add_argument("--gallery", type=Path, default=GALLERY_DIR, help=f"the gallery folder (default: {GALLERY_DIR})")
    parser.add_argument("--pool", type=Path, default=POOL_FILE, help=f"the pool of purchases (default: {POOL_FILE})")
    args = parser.parse_args(argv)

    pool = load_pool(args.pool) if args.pool.exists() else None
    try:
        if args.command == "review":
            print(render_review(review_folder(args.folder, pool)))
            return 0
        if args.command == "promote":
            for path in promote(args.files, args.gallery, pool, args.why):
                print(f"promoted {path}")
        elif args.command == "remove":
            remove(args.ids, args.gallery, pool)
            print(f"removed {', '.join(args.ids)}")
        index = write_index(args.gallery, pool) if args.command == "index" else json.loads((args.gallery / INDEX_NAME).read_text())
        print(f"{args.gallery / INDEX_NAME}: {index['count']} session(s)")
        return 0
    except SessionError as error:
        print("Nothing changed: " + "; ".join(error.problems), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
