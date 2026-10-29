"""Cost per use. Pure arithmetic: the same inputs always give the same answer.

The model's job is to estimate the inputs (how often, how long). This code's job
is to do the math, because a small model gets arithmetic wrong.

Resale is handled in code too. The model names a category and this tool looks up the
estimate itself. Early testing showed the model would invent a resale dollar amount if
allowed to type one, so that input does not exist.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from tools.resale import Category, ResaleInput, estimate_resale, years_text

WEEKS_PER_YEAR = 52


class CostPerUseInput(BaseModel):
    # Unknown fields are errors, not silently ignored. If the model tries to pass a
    # made-up `resale_value`, it gets told that field does not exist.
    model_config = ConfigDict(extra="forbid")

    price: float = Field(gt=0, le=100_000, description="Purchase price in dollars. Use the price the user gave.")
    uses_per_week: float = Field(
        gt=0, le=100, description="Your estimate of how many times a week it will be used. This is an assumption."
    )
    years: float = Field(
        gt=0, le=15, description="Your estimate of how many years the user will realistically keep using it."
    )
    category: Optional[Category] = Field(
        default=None,
        description="The kind of gadget. If given, the tool subtracts a rough estimated resale value from the cost. "
        "Never type a resale amount yourself.",
    )


def cost_per_use(args: CostPerUseInput) -> dict:
    resale_value = 0.0
    if args.category:
        resale = estimate_resale(ResaleInput(price=args.price, category=args.category, years_owned=args.years))
        resale_value = resale["estimated_resale_value"]

    total_uses = args.uses_per_week * WEEKS_PER_YEAR * args.years
    net_cost = args.price - resale_value
    per_use = net_cost / total_uses
    per_month = net_cost / (args.years * 12)

    resale_note = (
        f" after a rough, unverified resale estimate of ${resale_value:,.2f}" if args.category else ""
    )
    return {
        "total_uses": round(total_uses),
        "resale_value_used": round(resale_value, 2),
        "net_cost": round(net_cost, 2),
        "cost_per_use": round(per_use, 2),
        "cost_per_month": round(per_month, 2),
        "summary": (
            f"Net cost ${net_cost:,.2f}{resale_note}, spread over about {total_uses:,.0f} uses "
            f"({args.uses_per_week:g} a week for {years_text(args.years)}), is about ${per_use:,.2f} per use."
        ),
    }
