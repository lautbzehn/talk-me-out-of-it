"""Saving, loading and listing session transcripts.

run_council returns a session as a plain dict. This file is the only place that puts one on disk
and takes one off it, so the rest of the engine never touches the sessions folder and the UI can
rely on every file there being valid.

  sessions/scratch/   everything you run yourself; git ignores it
  sessions/gallery/   the sessions curated for the site; git keeps it

Three rules, each there for a reason:
- A session is checked (session_schema.check_session) before it is written, and again when it is read.
  A file that gets past both can be read by the UI without surprises.
- A file is written whole or not at all: the text goes to a temporary file first, then one rename puts it
  in place. A crash or a full disk can leave a stray temporary file but never a half-written session.
- The file name comes from the session itself (when it started and the item), so saving the same session
  twice replaces the file instead of making a copy.

Check what is in a folder with:  .venv/bin/python -m session_store [folder or files]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from session_schema import SessionError, check_session, parse_session

SESSIONS_DIR = Path("sessions")
SCRATCH_DIR = SESSIONS_DIR / "scratch"
GALLERY_DIR = SESSIONS_DIR / "gallery"
INDEX_NAME = "index.json"  # the gallery's list of its sessions (gallery.py); never a session itself


def slug(text: str, limit: int = 40) -> str:
    """"Noise-cancelling headphones" becomes "noise-cancelling-headphones": lowercase letters, digits, single hyphens."""
    words = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return words[:limit].strip("-") or "session"


def session_id(session: dict) -> str:
    """When the session started (UTC) and what it was about, such as "20261028-234929-laptop"."""
    session = parse_session(session)
    started = session.created_at.astimezone(timezone.utc)
    return f"{started:%Y%m%d-%H%M%S}-{slug(session.purchase.item)}"


def write_json_atomic(path: Path, data) -> Path:
    """Write `data` as readable JSON to `path`, whole or not at all: the text goes to a hidden temporary file in
    the same folder, then one rename puts it in place. Raises SessionError for data that is not plain JSON."""
    try:
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    except (TypeError, ValueError) as error:
        raise SessionError(f"the session is not plain JSON data: {error}") from error
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.tmp"
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)  # one step: the file is the old one or the new one, never half of either
    return path


def save_session(session: dict, folder: Path = SCRATCH_DIR) -> Path:
    """Check the session, write it as JSON in `folder`, and return the path. Raises SessionError, writing nothing,
    if the session breaks the contract."""
    name = session_id(session)  # also checks the session
    return write_json_atomic(Path(folder) / f"{name}.json", session)  # turns it into text before making any folder


def load_session(path: Path) -> dict:
    """Read a session file and check it. Raises SessionError with a plain message when the file is
    missing, is not JSON, or breaks the contract."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SessionError(f"{path} does not exist") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise SessionError(f"{path.name} is not valid JSON: {error}") from error
    problems = check_session(data)
    if problems:
        raise SessionError(problems)
    return data


def summarize(session: dict, path: Path | None = None) -> dict:
    """The few facts a gallery card or a list row needs, without opening the whole transcript."""
    checked = parse_session(session)
    scoring = session.get("scoring") or {}
    return {
        "id": session_id(session),
        "file": path.name if path else None,
        "kind": checked.kind,
        "item": checked.purchase.item,
        "price": checked.purchase.price,
        "want_level": checked.purchase.want_level,
        "current_device": checked.purchase.current_device,
        "created_at": session["created_at"],
        "model": checked.model,
        "verdict": scoring.get("verdict"),
        "verdict_label": scoring.get("verdict_label"),
        "score": scoring.get("score"),
        "rail": scoring.get("rail"),
        "rail_note": scoring.get("rail_note"),  # code-written sentence for the verdict card
        "rounds": len(checked.rounds),
        "seconds": checked.timing.total_seconds,
        "ruling": (session.get("judge") or {}).get("ruling"),
        "why_featured": (session.get("gallery") or {}).get("why_featured"),
        "judge_fallback": (session.get("judge") or {}).get("fallback_used"),
    }


def list_sessions(folder: Path = SCRATCH_DIR) -> list[dict]:
    """A summary for every session file in `folder`, newest first. A file that cannot be read is listed with its
    problems instead of stopping the list, so one bad file never hides the rest."""
    good, bad = [], []
    for path in sorted(p for p in Path(folder).glob("*.json") if p.name != INDEX_NAME):
        try:
            good.append(summarize(load_session(path), path))
        except SessionError as error:
            bad.append({"file": path.name, "problems": error.problems})
    # By when the session started, not by file name: eval runs name their files after the scenario.
    # ISO timestamps with the same offset sort correctly as text, but the offset can differ, so compare real times.
    good.sort(key=lambda entry: datetime.fromisoformat(entry["created_at"]), reverse=True)
    return good + bad


def describe(entry: dict) -> str:
    if "problems" in entry:
        return f"BAD  {entry['file']}: {'; '.join(entry['problems'])}"
    if entry["kind"] == "declined":
        outcome = "declined"
    else:
        held = " (held by a rule)" if entry["rail"] else ""
        outcome = f"{entry['verdict_label']} {entry['score']}{held}"
    minutes, seconds = divmod(round(entry["seconds"]), 60)
    return f"OK   {entry['id']}  {entry['item']} · ${entry['price']:,.0f} · {outcome} · {minutes}m {seconds:02d}s"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="List and check saved sessions.")
    parser.add_argument("paths", nargs="*", type=Path, help=f"folders or files (default: {SCRATCH_DIR})")
    args = parser.parse_args(argv)

    entries = []
    for path in args.paths or [SCRATCH_DIR]:
        if path.is_dir():
            print(f"{path}")
            entries += list_sessions(path)
        else:
            try:
                entries.append(summarize(load_session(path), path))
            except SessionError as error:
                entries.append({"file": path.name, "problems": error.problems})
    for entry in entries:
        print("  " + describe(entry))
    bad = sum("problems" in entry for entry in entries)
    print(f"\n{len(entries) - bad} fine, {bad} with problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
