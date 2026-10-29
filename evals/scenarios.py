"""The eval scenarios: purchases with the verdict a sensible person would expect.

An eval (short for evaluation) is a test for behavior that has no single exact answer.
A unit test checks that the cost-per-use math is right to the cent. An eval runs the real
council on purchases where people would agree on the right call, and counts how often the
council agrees too. The expected verdicts live in scenarios.json and were written before
any eval run, so the council is measured against people, not against itself.

This file only loads and checks the list. The eval runner (Phase 5 step 2) runs it.
"""

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agents.schemas import Purchase
from tools.resale import Category

SCENARIOS_FILE = Path(__file__).parent / "scenarios.json"

# The three verdicts, plus "declined": the intake check should turn the input away.
Expected = Literal["buy", "wait", "skip", "declined"]


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")  # lowercase words joined by dashes; used in file names
    expected: Expected
    category: Optional[Category]  # what a correct intake check picks; None when more than one would be fair
    tags: list[str]
    why_expected: str = Field(min_length=10)  # the reason a person would give, for the report
    purchase: Purchase

    @field_validator("purchase", mode="before")
    @classmethod
    def no_unknown_purchase_fields(cls, value):
        """Purchase ignores fields it doesn't know, so a typo like "current_devise" would quietly
        become "no current device" and change the scenario. Here a typo is an error."""
        if isinstance(value, dict):
            unknown = set(value) - set(Purchase.model_fields)
            if unknown:
                raise ValueError(f"unknown purchase field(s): {', '.join(sorted(unknown))}")
        return value

    @model_validator(mode="after")
    def declined_has_no_category(self):
        if self.expected == "declined" and self.category is not None:
            raise ValueError("a declined scenario is not a gadget, so its category must be null")
        return self


class ScenarioSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(pattern=r"^v\d+\.\d+$")
    date: str = Field(pattern=r"^\d{2}\.\d{2}\.\d{4}$")
    about: str
    scenarios: list[Scenario] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_are_unique(self):
        ids = [scenario.id for scenario in self.scenarios]
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        if repeated:
            raise ValueError(f"scenario ids must be unique: {', '.join(repeated)}")
        return self


def load_scenarios(path: Path = SCENARIOS_FILE) -> ScenarioSet:
    """Read and check the file. A mistake fails here in a second, not 40 minutes into an eval run."""
    return ScenarioSet.model_validate(json.loads(path.read_text()))
