"""Phase 2 demo: The Analyst gives a validated, structured take on two purchases.

Run with:  .venv/bin/python demo_phase2.py
"""

from agents.analyst import ANALYST
from agents.base import StructuredOutputError
from agents.council_agent import open_turn
from agents.schemas import Purchase

SAMPLES = [
    Purchase(
        item="Noise-cancelling headphones",
        price=350,
        why="I commute 90 minutes a day on a loud train and my cheap earbuds can't block it out.",
        want_level=7,
        current_device="Cheap wired earbuds",
    ),
    Purchase(
        item="PlayStation 5 Pro",
        price=700,
        why="My PS5 works fine, but the Pro looks sharper in the videos I've watched.",
        want_level=8,
        current_device="PlayStation 5",
    ),
]


def show_attempts(attempts):
    for a in attempts:
        status = "valid" if a["ok"] else f"rejected: {a['error']}"
        print(f"  attempt {a['attempt']}: {a['seconds']}s, {a['output_tokens']} tokens, {status}")


def main():
    for purchase in SAMPLES:
        print("=" * 70)
        print(f"{purchase.item} · ${purchase.price:,.0f} · wants it {purchase.want_level}/10")
        print("-" * 70)
        try:
            take, trace, _ = open_turn(ANALYST, purchase, use_tools=False)
            attempts = trace["attempts"]
        except StructuredOutputError as error:
            print(f"{ANALYST.name} could not produce a valid reply.")
            show_attempts(error.attempts)
            continue
        except ConnectionError:
            print("Can't reach Ollama. Start it with:  brew services start ollama")
            break

        print(f"{ANALYST.name}: {take.take}\n")
        for name, rating in take.ratings:
            print(f"  {name:<14} {rating.score:>2}/10  {rating.reason}")
        print(f"\n  lean: {take.lean.upper()}   confidence: {take.confidence}/10")
        print("\nAttempt log:")
        show_attempts(attempts)
    print("=" * 70)


if __name__ == "__main__":
    main()
