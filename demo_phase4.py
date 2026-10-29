"""Phase 4 demo: the whole council, end to end, live.

For each purchase, run_council does everything: the intake check, the opening round,
the rebuttal round, a tiebreak if the council is split, scoring in code, and the Judge.
This file only listens to its events and prints them, then shows the verdict card.
The last sample is not a gadget, to show the polite decline.

Each session is also saved to sessions/scratch/ (ignored by git) by the session store, so you can open the raw JSON.

Run with:  .venv/bin/python demo_phase4.py
"""

from agents.schemas import Purchase
from council import CouncilError, run_council
from demo_phase2 import SAMPLES
from display import ProgressChat, on_event, verdict_card
from session_store import save_session

SOFA = Purchase(item="Leather sofa", price=1200, why="My old couch sags in the middle.", want_level=6)


def main():
    for purchase in [*SAMPLES, SOFA]:
        print("=" * 72)
        print(f"{purchase.item} · ${purchase.price:,.0f} · wants it {purchase.want_level}/10")
        print(f"Why: {purchase.why}")
        print("=" * 72)
        try:
            session = run_council(purchase, chat=ProgressChat(), on_event=on_event)
        except CouncilError as error:
            print(f"\nThe council stopped: {error}")
            continue
        except ConnectionError:
            print("Can't reach Ollama. Start it with:  brew services start ollama")
            return

        if session["kind"] == "declined":
            print(f"\n{session['message']}")
        else:
            verdict_card(session)
        print(f"\n  Session saved: {save_session(session)}\n")


if __name__ == "__main__":
    main()
