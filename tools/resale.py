"""Resale value estimator. Pure arithmetic on a depreciation curve.

IMPORTANT: the percentages below are rough rules of thumb chosen for this project.
They are NOT market data, and the model's own product knowledge is out of date, so
every result is labeled an unverified estimate. If you want better numbers, this
table is the one place to tune them.

How the curve works: a device loses `first_year` of its price in year one, then
`later_years` of its remaining value each year after that.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["video_game", "console", "audio", "video", "computer", "phone", "camera", "wearable", "smart_home"]

# category: (share of price lost in year one, share of remaining value lost each later year)
DEPRECIATION = {
    "video_game": (0.45, 0.20),
    "console": (0.20, 0.12),
    "audio": (0.30, 0.15),
    "video": (0.35, 0.18),
    "computer": (0.30, 0.20),
    "phone": (0.35, 0.25),
    "camera": (0.20, 0.12),
    "wearable": (0.40, 0.25),
    "smart_home": (0.40, 0.25),
}


LABEL = {  # with the right article, so sentences read naturally
    "video_game": "a video game",
    "console": "a game console",
    "audio": "an audio device",
    "video": "a video device",
    "computer": "a computer",
    "phone": "a phone",
    "camera": "a camera",
    "wearable": "a wearable",
    "smart_home": "a smart home device",
}


def years_text(years: float) -> str:
    """"1 year" or "2.5 years", so tool summaries read naturally."""
    return f"{years:g} year" if years == 1 else f"{years:g} years"


class ResaleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: float = Field(gt=0, le=100_000, description="Purchase price in dollars. Use the price the user gave.")
    category: Category = Field(description="The kind of gadget. Pick the closest match.")
    years_owned: float = Field(gt=0, le=15, description="How many years until the user would sell it.")


def estimate_resale(args: ResaleInput) -> dict:
    first_year, later_years = DEPRECIATION[args.category]
    value = (
        args.price
        * (1 - first_year) ** min(args.years_owned, 1)
        * (1 - later_years) ** max(args.years_owned - 1, 0)
    )
    return {
        "estimated_resale_value": round(value, 2),
        "estimated_loss": round(args.price - value, 2),
        "percent_retained": round(100 * value / args.price),
        "label": "rough rule-of-thumb estimate, unverified, not a market price",
        "summary": (
            f"{LABEL[args.category].capitalize()} bought for ${args.price:,.2f} might resell for about "
            f"${value:,.2f} after {years_text(args.years_owned)}. This is a rough estimate, not a market price. "
            "Check real resale listings before relying on it."
        ),
    }
