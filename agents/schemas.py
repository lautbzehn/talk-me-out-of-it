"""The shapes of data that flow through the council.

Pydantic models do two jobs here:
1. Describe the shape, so Ollama can force the model's reply to match it.
2. Check the rules (ranges, lengths, allowed words), so a bad reply is caught
   and retried instead of slipping through.

One convention for every rating in the project: 10 always means "this point
favors buying" and 1 means "this point argues against buying". Keeping one
direction everywhere makes the Phase 5 scoring code simple and easy to audit.
"""

import re
from typing import Annotated, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from tools.resale import Category

# A score is a whole number from 1 to 10. Defined once, reused everywhere.
Score = Annotated[int, Field(ge=1, le=10)]

# The three verdicts the council can reach, and the only words an agent may lean toward.
Lean = Literal["buy", "wait", "skip"]

# The four council members who rate, in speaking order. agents/roster.py must match it (a test checks).
AgentName = Literal["The Analyst", "Future You", "Budget Guardian", "Alternatives Hunter"]


def count_sentences(text: str) -> int:
    """A sentence ends with . ! or ? followed by a space (a closing quote may sit in between),
    so the point in "$0.22" is not a break. The last sentence needs no final period."""
    return len([part for part in re.split(r"[.!?]+[\"'”’)]*\s+", text.strip()) if part.strip()])


# Grounding: an agent or the Judge may only write numbers that appear in what it was given:
# the purchase, its tool results, and the debate. The caller passes them as context.
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# A whole number right before a unit of time is a duration ("12 months", "a 24-month plan"). It is an
# assumption about time, not a price or a calculation, and the 14B Hunter lost a whole turn to "12 months".
# "$12" and "12%" are still checked.
DURATION = re.compile(r"[\s-]*(?:days?|weeks?|months?|years?)\b", re.IGNORECASE)


def number_values(text: str) -> set[float]:
    """Every number in a text, as values: "$1,560.00" and "1560" are the same number."""
    return {float(match.replace(",", "")) for match in NUMBER.findall(text) if match.replace(",", "")}


def ungrounded_numbers(text: str, known: set[float]) -> list[str]:
    """Numbers in `text` that are not in `known`. Whole numbers up to 10 are always allowed:
    they are scores, rounds, and counts of agents. So are whole-number durations. Rounding a
    known number is allowed too: in a live run the Analyst wrote "$336" for the tool's $335.83,
    which is not inventing, while no number in the debate rounds to the "$300" Future You once made up."""
    allowed = known | {float(round(k)) for k in known} | {round(k, 1) for k in known}
    unknown = []
    for match in NUMBER.finditer(text):
        value = float(match.group().replace(",", ""))
        if value.is_integer() and (value <= 10 or DURATION.match(text, match.end())):
            continue
        if value not in allowed:
            unknown.append(match.group().rstrip(","))
    return unknown


def closest_known(value: float, known: set[float]) -> float | None:
    """The number the model was given that is nearest to `value`, if it is within 10%. A retry that only
    says "not a number you were given" got the same number back every time (the 14B wrote "about $335"
    for the tool's $335.83). A number far from everything, like a "66%" it worked out itself, gets no
    suggestion: a wrong hint is worse than none."""
    near = [k for k in known if k != value and abs(k - value) <= 0.1 * abs(value)]
    return min(near, key=lambda k: abs(k - value), default=None)


def show_number(value: float) -> str:
    """335.83 stays "335.83", 1560.0 becomes "1,560": the way the number appeared in the first place."""
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def check_grounded(text: str, info: ValidationInfo) -> str:
    known = (info.context or {}).get("known_numbers")
    if known is not None:
        unknown = ungrounded_numbers(text, known)
        if unknown:
            message = (
                f"{', '.join(unknown)} is not a number you were given; use numbers only exactly as they appear "
                "in the purchase, the tool results, or the debate, or leave the number out, "
                "and never work one out yourself"
            )
            hints = []
            for number in unknown:
                near = closest_known(float(number.replace(",", "")), known)
                if near is not None:
                    hints.append(f"{show_number(near)} instead of {number}")
            if hints:
                message += f". If you meant a number you were given, write it exactly: {'; '.join(hints)}"
            raise ValueError(message)
    return text


# Every text a viewer will read passes check_clean. Two ways the model breaks text without noticing:

# 1. Qwen sometimes switches to Chinese mid-sentence ("better picture质量", "Both options can挠").
#    Chinese, Japanese and Korean characters and full-width punctuation: none belongs in this debate.
CJK = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff00-\uffef]")

# 2. Ollama closes a string the moment it reaches its max_length, and the reply still looks normal
#    ("...leading to a verdict of Wait"). A text within two characters of its limit (slack for how the
#    limit is counted) that does not end like a sentence was cut off.
CUT_OFF_SLACK = 2
ENDS_A_SENTENCE = re.compile(r"[.!?][\"'”’)]*\s*$")


def text_limit(model: type[BaseModel], field: str) -> int:
    """The max_length a schema puts on a text field, read from the schema so it can't drift."""
    for rule in model.model_fields[field].metadata:
        if getattr(rule, "max_length", None) is not None:
            return rule.max_length
    raise ValueError(f"{model.__name__}.{field} has no max_length")


def is_cut_off(text: str, limit: int) -> bool:
    return len(text) >= limit - CUT_OFF_SLACK and not ENDS_A_SENTENCE.search(text)


def check_clean(cls, text: str, info: ValidationInfo) -> str:
    """Reused by every model text field. A reply rebuilt from a saved session (context "saved") was
    accepted under the rules of its day, so it is not judged again by rules added later."""
    if (info.context or {}).get("saved"):
        return text
    foreign = CJK.findall(text)
    if foreign:
        raise ValueError(f"write only in English; this text has Chinese characters in it ({''.join(dict.fromkeys(foreign))})")
    limit = text_limit(cls, info.field_name)
    if is_cut_off(text, limit):
        raise ValueError(
            f"this text reached its {limit}-character limit and was cut off mid-sentence; "
            "write a shorter version that is complete and ends with a period"
        )
    return text


class Purchase(BaseModel):
    """What the user tells the council. These are the only inputs."""

    item: str = Field(min_length=2, max_length=100)
    price: float = Field(gt=0, le=100_000)
    why: str = Field(min_length=3, max_length=500)
    want_level: Score
    current_device: Optional[str] = Field(default=None, max_length=100)


class Rating(BaseModel):
    """One rubric item. The reason comes before the score on purpose: the model
    writes fields in order, so it explains itself before it commits to a number."""

    reason: str = Field(min_length=5, max_length=200)
    score: Score

    _reason_clean = field_validator("reason")(check_clean)

    @field_validator("reason")
    @classmethod
    def no_score_inside_reason(cls, text: str) -> str:
        """A custom rule. Small models like to put a score in the reason too: at the start
        ("8/10 - ...", "9 = ...") or at the end ("... 6/10 for improvement."). That duplicates
        the real score and can contradict it, so it is rejected and retried. "N/10" and
        "N out of 10" are rejected anywhere. A reason like "3-5 years of use" is still fine.
        The 14B wrote the want level this way ("as intense as a 7/10 would suggest") and twice sent
        the same text back, so the message now quotes what it found and says what to write instead."""
        if re.match(r"\s*\d{1,2}\s*(?:[=:]|-\s)", text):
            raise ValueError("start the reason with words, not a score; the number belongs in the score field")
        found = re.search(r"\b(\d{1,2})(?:\.\d+)?\s*(?:/|out of)\s*10\b", text)
        if found:
            raise ValueError(
                f'never write a number out of 10 in a reason, not even the want level ("{found.group()}"); '
                f'if you mean how badly they want it, write "their want level of {found.group(1)}" instead, '
                "and put your own number in the score field"
            )
        return text

    _reason_grounded = field_validator("reason")(check_grounded)


class AnalystRatings(BaseModel):
    """The Analyst's rubric. Each description is the scoring guide, and the same
    text is shown to the model in its prompt, so the rubric lives in one place."""

    value_per_use: Rating = Field(
        description="10 = the price is easily justified by how often and how much it will be used. "
        "1 = expensive for how little it will be used."
    )
    longevity: Rating = Field(
        description="10 = likely to stay useful for many years. 1 = likely to feel outdated or wear out soon."
    )
    upgrade_gap: Rating = Field(
        description="10 = a big real-world improvement over the device it replaces (or over nothing). "
        "1 = barely different from what they already have."
    )


class FutureYouRatings(BaseModel):
    """Future You's rubric, scored as the user six months from now."""

    six_month_glow: Rating = Field(
        description="10 = six months on, I am still glad I bought it. 1 = it is the purchase I avoid mentioning."
    )
    want_vs_reason: Rating = Field(
        description="10 = the reason they gave fully justifies how badly they want it. "
        "1 = the want runs far ahead of the reason."
    )
    use_reality: Rating = Field(
        description="10 = it gets used as much as they imagine. 1 = it sits in a drawer."
    )


class BudgetGuardianRatings(BaseModel):
    """Budget Guardian's rubric: opportunity cost, in the user's own terms."""

    price_for_the_problem: Rating = Field(
        description="10 = a modest price for the problem they described. 1 = a lot of money for that problem."
    )
    cost_of_waiting: Rating = Field(
        description="10 = waiting 30 days would cost them something real. 1 = nothing is lost by waiting."
    )
    # Compared with keeping the money, not with other purchases. The earlier key, money_elsewhere,
    # invited lists like "an emergency fund or a small vacation". In a live A/B test the old key
    # listed other uses in 4 of 5 answers even with this wording; this key did in 0 of 6.
    better_than_keeping_it: Rating = Field(
        description="10 = from what they told you, this is a better use of the money than keeping it. "
        "1 = they would likely be happier keeping the money for now. "
        "Judge only from what they told you, and never list other ways to spend or save it."
    )


UNVERIFIED_LABEL = "Unverified: "


class AlternativesHunterRatings(BaseModel):
    """Alternatives Hunter's rubric: cheaper paths, release timing, and lock-in."""

    # Named positively on purpose. An earlier key, no_cheaper_path, was a double negative
    # and the model scored it backwards in every live run.
    worth_full_price: Rating = Field(
        description="10 = paying full price for this exact item is the best way to get what they want. "
        "1 = refurbished, last year's model, or a cheaper option gets most of the same benefit."
    )
    release_timing: Rating = Field(
        description="10 = a newer model is unlikely soon. 1 = a newer model is likely soon. "
        "Judge from how often this kind of gadget usually gets a new version, "
        "and say in the reason that the timing is unverified."
    )
    ecosystem_freedom: Rating = Field(
        description="10 = no lock-in worry. "
        "1 = it pulls them deeper into one brand's ecosystem in a way that costs more later."
    )

    @field_validator("release_timing", mode="before")
    @classmethod
    def label_timing_unverified(cls, rating):
        """The model's product knowledge is out of date, so release timing is always a guess and must say so.
        The prompt asks for the label, and the 14B left it out in 16 of 39 councils, each time costing a whole
        retry for one missing word. The label is a fixed word that changes nothing else in the sentence, so
        code adds it instead. This runs before the Rating's own checks, so the labeled reason still has to
        fit its length limit; when it would not fit, the rule below asks the model as before."""
        if isinstance(rating, dict) and isinstance(rating.get("reason"), str):
            reason = rating["reason"]
            labeled = f"{UNVERIFIED_LABEL}{reason.strip()}"
            if "unverified" not in reason.lower() and len(labeled) <= text_limit(Rating, "reason"):
                rating = {**rating, "reason": labeled}
        return rating

    @field_validator("release_timing")
    @classmethod
    def timing_is_labeled_unverified(cls, rating: Rating) -> Rating:
        if "unverified" not in rating.reason.lower():
            raise ValueError('say in the reason that the release timing is unverified, for example "unverified, but ..."')
        return rating


# A placeholder for "whichever rubric this agent uses". Each agent fills it in.
RatingsT = TypeVar("RatingsT", bound=BaseModel)


class AgentTake(BaseModel, Generic[RatingsT]):
    """What every council agent returns in the opening round.

    The outer shape is shared by all agents, so the orchestrator, scoring, and UI
    can treat them the same way. Only the ratings inside differ, one rubric per agent.
    Use it like this: AgentTake[AnalystRatings].

    The agent's name is not in here. The code already knows who is speaking,
    so asking the model to type its own name would only add a way to be wrong.
    """

    # 60 characters rules out a very short take. The sentence rule below does the rest.
    take: str = Field(min_length=60, max_length=500)
    ratings: RatingsT
    lean: Lean
    confidence: Score

    _take_clean = field_validator("take")(check_clean)

    @field_validator("take")
    @classmethod
    def at_least_two_sentences(cls, text: str) -> str:
        """The prompt asks for 2 or 3 sentences. Live testing showed one long sentence slips
        past any length rule, so code counts them."""
        if count_sentences(text) < 2:
            raise ValueError("write at least two full sentences; this take has only one")
        return text

    _take_grounded = field_validator("take")(check_grounded)


def is_addressed(name: str, text: str) -> bool:
    """True if `text` mentions the agent: its full name ("The" optional), or its last word when
    that word is distinctive ("Analyst", "Guardian", "Hunter"). "You" alone is far too common,
    so Future You has to be named in full."""
    text = text.lower()
    full = name.lower().removeprefix("the ")
    last = full.split()[-1]
    return full in text or (last != "you" and re.search(rf"\b{last}\b", text) is not None)


class AgentRebuttal(BaseModel, Generic[RatingsT]):
    """What every council agent returns in a rebuttal round: who it answers, what it says to
    them, and its own rubric scored again. Use it like this: AgentRebuttal[AnalystRatings].

    `responding_to` comes first on purpose. The model decides who it is talking to, then
    writes the response, which makes it more likely to name them.

    Two rules need to know who is speaking and who spoke last round. The caller passes that
    as validation context: {"self": "The Analyst", "speakers": ["Future You", ...]}. Without
    a context those two rules are skipped, so the shape can still be checked on its own.
    Whether an agent changed its mind is never asked here. Code works it out from the numbers.
    """

    # At most two, so a rebuttal argues with someone instead of summarizing everyone.
    responding_to: list[AgentName] = Field(min_length=1, max_length=2)
    response: str = Field(min_length=40, max_length=500)
    ratings: RatingsT
    lean: Lean
    confidence: Score

    _response_clean = field_validator("response")(check_clean)

    @field_validator("responding_to")
    @classmethod
    def only_others_who_spoke(cls, names: list[str], info: ValidationInfo) -> list[str]:
        names = list(dict.fromkeys(names))  # drop repeats, keep the order
        context = info.context or {}
        me = context.get("self")
        if me in names:
            raise ValueError(f"you are {me}; respond to the other council members, not yourself")
        speakers = context.get("speakers")
        if speakers is not None:
            absent = [name for name in names if name not in speakers]
            if absent:
                raise ValueError(
                    f"{', '.join(absent)} did not speak last round; choose from: {', '.join(speakers)}"
                )
        return names

    @field_validator("response")
    @classmethod
    def names_who_it_answers(cls, text: str, info: ValidationInfo) -> str:
        # Fields are checked in order, so responding_to is already in info.data (if it passed).
        names = info.data.get("responding_to")
        if names and not any(is_addressed(name, text) for name in names):
            raise ValueError(
                f"speak to them by name in the response: {', '.join(names)}"
            )
        return text

    _response_grounded = field_validator("response")(check_grounded)


class Intake(BaseModel):
    """The check that runs before the council: is this a tech gadget, and which kind?
    Not a council member: it has no voice and no ratings. The note comes first, so the
    model says what the item is before it decides.

    `why_has_instructions` is the second layer of the injection guard (agents/guard.py):
    a "why" that gives the council orders instead of a reason is set aside."""

    note: str = Field(min_length=5, max_length=200)
    why_has_instructions: bool
    is_tech_gadget: bool
    category: Optional[Category] = None

    @model_validator(mode="after")
    def category_matches_the_answer(self):
        if self.is_tech_gadget and self.category is None:
            raise ValueError("it is a tech gadget, so pick the closest category")
        if not self.is_tech_gadget:
            self.category = None  # a category means nothing for something that is not a gadget
        return self


def check_speaker(name: str, info: ValidationInfo) -> str:
    speakers = (info.context or {}).get("speakers")
    if speakers is not None and name not in speakers:
        raise ValueError(f"{name} gave no final answer; choose from: {', '.join(speakers)}")
    return name


class Point(BaseModel):
    """One council member's argument, picked out by the Judge."""

    agent: AgentName
    point: str = Field(min_length=10, max_length=200)

    _agent_spoke = field_validator("agent")(check_speaker)
    _point_clean = field_validator("point")(check_clean)
    _point_grounded = field_validator("point")(check_grounded)


# A verdict word, or its -ing form, as the first word ("Wait 30 days...", "Skip: ...", "Skipping the purchase...").
VERDICT_FIRST = re.compile(r"\W*(?:buy|buying|wait|waiting|skip|skipping)\b", re.IGNORECASE)


class Ruling(BaseModel):
    """The Judge's explanation of the verdict that code already reached.

    There is no verdict field and no score field, on purpose: the model judges, the code
    calculates. The Judge explains a result; it cannot produce one.

    The one-sentence ruling comes last, after the Judge has laid out the debate, for the
    same reason a rating's reason comes before its score.
    Context for the rules: {"speakers": [...], "known_numbers": {...}}.

    The model sees the ruling's key as `main_reason`, while code and saved sessions call it `ruling`
    (an alias). Key names are prompts: under `ruling` the 14B opened with the verdict in 37 of 52
    councils ("Wait 30 days to explore cheaper alternatives."), under `main_reason` in 0 of 6 reruns."""

    model_config = ConfigDict(validate_by_name=True)

    summary: str = Field(min_length=40, max_length=500)
    strongest_for: Point
    strongest_against: Point
    most_persuasive: AgentName
    would_change_verdict: str = Field(min_length=10, max_length=200)
    ruling: str = Field(min_length=20, max_length=160, alias="main_reason")

    _texts_clean = field_validator("summary", "would_change_verdict", "ruling")(check_clean)
    _texts_grounded = field_validator("summary", "would_change_verdict", "ruling")(check_grounded)
    _persuader_spoke = field_validator("most_persuasive")(check_speaker)

    @field_validator("summary")
    @classmethod
    def two_or_three_sentences(cls, text: str) -> str:
        found = count_sentences(text)
        if not 2 <= found <= 3:
            raise ValueError(
                f"the summary has {found} sentence(s); split it into 2 or 3 short sentences, each ending with a period"
            )
        return text

    @field_validator("ruling")
    @classmethod
    def one_complete_sentence(cls, text: str) -> str:
        """Ollama enforces the 160 character limit while the model writes, so a long ruling is
        cut off mid-word and still fits. Live run: "...waiting a month could help find a".
        Requiring a real ending catches that and sends it back. Stricter than check_clean:
        the verdict card shows this sentence, so it must end properly at any length."""
        if count_sentences(text) != 1:
            raise ValueError("main_reason must be exactly one sentence")
        if not text.rstrip().endswith((".", "!", "?")):
            raise ValueError("main_reason must end with a period; if it was cut off, write one shorter sentence")
        return text

    @field_validator("ruling")
    @classmethod
    def not_the_verdict_again(cls, text: str) -> str:
        """The verdict card shows the verdict right above this sentence, so "Wait 30 days to..." says it twice.
        Rejected, not stripped: the verdict word is usually the verb ("Skip due to the high price"), so
        cutting it off leaves a fragment ("due to the high price"). That was 34 of 37 real cases."""
        if VERDICT_FIRST.match(text):
            raise ValueError(
                "do not start main_reason with the verdict; the verdict card already shows it right above "
                "this sentence, so start with the reason itself"
            )
        return text
