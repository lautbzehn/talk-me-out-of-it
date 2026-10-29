"""Shared helper for turning Pydantic's long error reports into one short line.

Used both when the model's final answer breaks a rule and when it passes bad
arguments to a tool. The short line is what we show back to the model."""

from pydantic import ValidationError


def summarize_errors(error: ValidationError) -> str:
    """Example result: "ratings.longevity.score: Input should be less than or equal to 10"."""
    problems = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"]) or "input"
        problems.append(f"{where}: {item['msg']}")
    return "; ".join(problems)
