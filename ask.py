"""Ask the council about one purchase from the command line.

You give it the same inputs the product takes: the item, the price, why you want it, how badly (1 to 10),
and optionally the device it would replace. It runs the whole council, shows the debate as it happens, prints
the verdict card, and saves the transcript with the session store (sessions/scratch/ by default, which git ignores).

  .venv/bin/python ask.py "Noise-cancelling headphones" --price 350 --want 7 \\
      --why "I commute 90 minutes a day on a loud train and my cheap earbuds can't block it out." \\
      --owns "Cheap wired earbuds"

A council takes about 7 minutes on the 14B model. Ollama has to be running (brew services start ollama).
"""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from agents.schemas import Purchase
from council import CouncilError, run_council
from display import ProgressChat, on_event, verdict_card
from session_store import SCRATCH_DIR, save_session
from validation import summarize_errors

DISCLAIMER = "This is a decision helper, not financial advice. Nothing was bought and no store was contacted."


def build_purchase(args) -> Purchase:
    return Purchase(item=args.item, price=args.price, why=args.why, want_level=args.want, current_device=args.owns)


def main(argv=None, chat=None, folder: Path = SCRATCH_DIR) -> int:
    """Returns the exit code: 0 when the council ran (or politely declined), 1 when it could not, 2 for bad input."""
    parser = argparse.ArgumentParser(description="Ask the council whether to buy a tech gadget.")
    parser.add_argument("item", help='what you are thinking of buying, such as "Noise-cancelling headphones"')
    parser.add_argument("--price", type=float, required=True, help="the price in dollars")
    parser.add_argument("--why", required=True, help="why you want it")
    parser.add_argument("--want", type=int, required=True, help="how badly you want it, 1 to 10")
    parser.add_argument("--owns", help="the device you have now that this would replace (optional)")
    parser.add_argument("--folder", type=Path, default=folder, help=f"where to save the transcript (default: {folder})")
    args = parser.parse_args(argv)

    try:
        purchase = build_purchase(args)
    except ValidationError as error:
        print(f"That purchase can't be checked: {summarize_errors(error)}", file=sys.stderr)
        return 2

    print("=" * 72)
    print(f"{purchase.item} · ${purchase.price:,.0f} · wants it {purchase.want_level}/10")
    print(f"Why: {purchase.why}")
    if purchase.current_device:
        print(f"Has now: {purchase.current_device}")
    print("=" * 72)
    try:
        session = run_council(purchase, chat=chat or ProgressChat(), on_event=on_event)
    except CouncilError as error:
        print(f"\nThe council stopped: {error}", file=sys.stderr)
        return 1
    except ConnectionError:
        print("Can't reach Ollama. Start it with:  brew services start ollama", file=sys.stderr)
        return 1

    if session["kind"] == "declined":
        print(f"\n{session['message']}")
    else:
        verdict_card(session)
    print(f"\n  Session saved: {save_session(session, args.folder)}")
    print(f"  {DISCLAIMER}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
