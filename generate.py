"""Generate gallery candidates: run purchases from the gallery pool through the real council and save them.

  .venv/bin/python -m generate                                    every purchase in sessions/gallery_pool.json
  .venv/bin/python -m generate --only ps5-pro-upgrade,leather-sofa
  .venv/bin/python -m generate --repeats 2                        two councils per purchase, to choose from

The whole pool is 12 councils and a decline, about 1.5 hours on the 14B. A long model run needs the lid open
and the Mac on power (on battery the 14B drains about 30% an hour). Each transcript is saved by the session
store into a new folder, sessions/scratch/candidates-<time>/, as soon as its council ends, so stopping early
keeps everything finished. At the end it prints the review (the same as `python -m gallery review <folder>`).
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from agents.base import default_chat
from council import CouncilError, run_council
from evals.report import minutes
from evals.run_evals import progress
from gallery import POOL_FILE, PoolEntry, load_pool, render_review, review_folder
from session_store import SCRATCH_DIR, save_session

MINUTES_PER_COUNCIL = 7  # the 14B's average in the eval runs


def pick(entries: list[PoolEntry], only: str | None) -> list[PoolEntry]:
    if not only:
        return entries
    wanted = [name.strip() for name in only.split(",") if name.strip()]
    known = {entry.id: entry for entry in entries}
    unknown = [name for name in wanted if name not in known]
    if unknown:
        raise SystemExit(f"Unknown pool id(s): {', '.join(unknown)}. Known: {', '.join(known)}")
    return [known[name] for name in wanted]


def generate(entries: list[PoolEntry], folder: Path, repeats: int = 1, chat=default_chat, say=print) -> list[dict]:
    """Run each entry `repeats` times and save every finished session. A council that stops (fewer than two members
    answering) is reported and skipped; it has no verdict, so it is no gallery material. Returns one line of
    facts per council. A ConnectionError (Ollama not running) is left to the caller: nothing after it would work."""
    results, total, done = [], len(entries) * repeats, 0
    for repeat in range(1, repeats + 1):
        for entry in entries:
            done += 1
            say(f"\n[{done}/{total}] {entry.id}: {entry.purchase.item}")
            started = time.perf_counter()
            try:
                session = run_council(entry.purchase, chat=chat, on_event=progress(say))
            except CouncilError as error:
                say(f"    council stopped, nothing saved: {error}")
                results.append({"id": entry.id, "repeat": repeat, "saved": None, "error": str(error)})
                continue
            path = save_session(session, folder)
            outcome = (session["scoring"] or {}).get("verdict_label") or "declined"
            say(f"    -> {outcome}, saved {path.name} ({minutes(time.perf_counter() - started)})")
            results.append({"id": entry.id, "repeat": repeat, "saved": path, "error": None})
    return results


def main(argv=None, chat=None, scratch: Path = SCRATCH_DIR) -> int:
    parser = argparse.ArgumentParser(description="Run gallery pool purchases through the council and save the transcripts.")
    parser.add_argument("--only", help="comma-separated pool ids to run, instead of all of them")
    parser.add_argument("--repeats", type=int, default=1, choices=range(1, 4), metavar="1-3",
                        help="councils per purchase (the model varies between runs)")
    parser.add_argument("--pool", type=Path, default=POOL_FILE, help=f"the pool of purchases (default: {POOL_FILE})")
    parser.add_argument("--out", type=Path, help="the folder to save into (default: a new candidates folder in scratch)")
    args = parser.parse_args(argv)

    pool = load_pool(args.pool)
    entries = pick(pool.purchases, args.only)
    folder = args.out or Path(scratch) / f"candidates-{datetime.now():%Y%m%d-%H%M%S}"
    runs = len(entries) * args.repeats
    print(f"Generating {runs} candidate session(s) into {folder}, roughly {runs * MINUTES_PER_COUNCIL} minutes."
          " Ctrl+C stops it and keeps everything finished.")
    try:
        generate(entries, folder, args.repeats, chat=chat or default_chat)
    except ConnectionError:
        print("Can't reach Ollama. Start it with:  brew services start ollama", file=sys.stderr)
        return 1
    print("\n" + "=" * 72 + "\nReview\n" + "=" * 72)
    print(render_review(review_folder(folder, pool)))
    print(f"\nPromote the chosen ones with:  .venv/bin/python -m gallery promote {folder}/<file>.json ...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
