"""The transcript contract: what a saved session has to look like.

The engine writes a session and the UI reads it. Nothing else connects them, so this file is the
agreement between the two. It checks two different things:

1. Shape (Pydantic): every field the UI will read is there, with the right type and an allowed word
   where it has to be one of a few (a lean is buy, wait or skip). Extra fields are fine, so the engine
   can add to a session without breaking older readers.
2. Story: the parts have to agree with each other. The score on the card must be what the saved
   ratings give, the verdict must follow from that score and the leans, and the ratings that were scored
   must be the ones each member gave in its last turn. "The model judges, the code calculates" is a
   promise about how sessions are made; this check makes it something a reader can verify, and it is why
   a gallery session cannot be edited by hand into a different verdict without being caught.

A session from an older formula is checked for shape and for its ratings matching the debate, but its
score is not recomputed, because it used other rules.

`check_session(data)` returns a list of plain-English problems (empty means fine). `parse_session(data)`
raises SessionError with the same list.
"""

from datetime import datetime
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

import scoring
from agents.schemas import Lean, Purchase, Score

SUPPORTED_SCHEMAS = (2, 3)  # 1 predates the injection guard; the first eval sessions are 2 and need no engine block
ROUND_KINDS = ("opening", "rebuttal", "tiebreak")


class SessionError(Exception):
    """A session is missing, unreadable, or breaks the contract. `problems` lists everything wrong."""

    def __init__(self, problems: list[str] | str):
        self.problems = [problems] if isinstance(problems, str) else list(problems)
        super().__init__("; ".join(self.problems))


class Record(BaseModel):
    """Every part of a session. Unknown extra fields are kept, not rejected."""

    model_config = ConfigDict(extra="allow")


class RatingRecord(Record):
    reason: str = Field(min_length=1)
    score: Score


class ReplyRecord(Record):
    """An agent's take (opening round) or rebuttal (later rounds), as saved."""

    ratings: dict[str, RatingRecord] = Field(min_length=1)
    lean: Lean
    confidence: Score
    take: Optional[str] = None
    response: Optional[str] = None
    responding_to: Optional[list[str]] = None

    @model_validator(mode="after")
    def says_one_thing(self):
        if (self.take is None) == (self.response is None):
            raise ValueError("a reply has either a take (opening) or a response (rebuttal), not both and not neither")
        return self


class TurnRecord(Record):
    agent: str = Field(min_length=1)
    status: Literal["ok", "failed"]
    take_or_rebuttal: Optional[ReplyRecord] = None
    changes: Optional[dict] = None
    seconds: float = Field(ge=0)
    trace: dict

    @model_validator(mode="after")
    def reply_matches_status(self):
        if self.status == "ok" and self.take_or_rebuttal is None:
            raise ValueError(f"{self.agent}'s turn is ok but has no reply")
        if self.status == "failed" and self.take_or_rebuttal is not None:
            raise ValueError(f"{self.agent}'s turn failed but has a reply")
        return self


class RoundRecord(Record):
    number: int = Field(ge=1)
    kind: Literal["opening", "rebuttal", "tiebreak"]
    seconds: float = Field(ge=0)
    turns: list[TurnRecord] = Field(min_length=1)


class ScoringRecord(Record):
    score: float = Field(ge=1, le=10)
    verdict: Lean
    verdict_label: str
    formula_version: int
    formula: str
    inputs: dict[str, dict[str, Score]] = Field(min_length=1)
    agent_averages: dict[str, float]
    ratings_counted: int = Field(ge=1)
    # Formula 2 and later: the leans the rails read, what the score alone said, and which rail (if any) held it.
    leans: Optional[dict[str, Lean]] = None
    score_verdict: Optional[Lean] = None
    rail: Optional[str] = None
    rail_note: Optional[str] = None

    @model_validator(mode="after")
    def formula_two_has_its_fields(self):
        if self.formula_version >= 2 and (self.leans is None or self.score_verdict is None):
            raise ValueError(f"formula {self.formula_version} scoring must record leans and score_verdict")
        return self


class PointRecord(Record):
    agent: str
    point: str


class JudgeRecord(Record):
    summary: str = Field(min_length=1)
    strongest_for: PointRecord
    strongest_against: PointRecord
    most_persuasive: str
    would_change_verdict: str = Field(min_length=1)
    ruling: str = Field(min_length=1)
    fallback_used: bool
    seconds: float = Field(ge=0)
    trace: dict


class AgentCard(Record):
    """One council member as the UI describes it: role, rubric, tools and the prompt it was given."""

    name: str
    focus: str
    voice: str
    rubric: dict[str, str] = Field(min_length=1)
    tools: list[str]
    required_tools: list[str]
    system_prompt: str = Field(min_length=1)


class EngineRecord(Record):
    """Schema 3: what the engine was when the session ran (see council.engine_snapshot)."""

    agents: list[AgentCard] = Field(min_length=2)
    tools: dict[str, str]
    prompts: dict[str, str]
    rules: dict


class IntakeRecord(Record):
    note: str
    is_tech_gadget: bool


class GuardRecord(Record):
    triggered: bool
    why_as_read: str


class TimingRecord(Record):
    total_seconds: float = Field(ge=0)


class GalleryNote(Record):
    """Added when a session is promoted to the gallery: what this session shows a visitor. It lives in the
    transcript, not the index, so rebuilding the index never loses it."""

    why_featured: str = Field(min_length=10)


class SessionBase(Record):
    schema_version: Literal[2, 3]
    created_at: datetime
    model: str = Field(min_length=1)
    purchase: Purchase  # as the user typed it
    intake: IntakeRecord
    guard: GuardRecord
    timing: TimingRecord
    gallery: Optional[GalleryNote] = None


class CouncilSession(SessionBase):
    kind: Literal["council"]
    engine: Optional[EngineRecord] = None
    rounds: list[RoundRecord] = Field(min_length=1)
    scoring: ScoringRecord
    judge: JudgeRecord

    @model_validator(mode="after")
    def schema_three_has_its_engine(self):
        if self.schema_version >= 3 and self.engine is None:
            raise ValueError("a schema 3 council session must carry its engine snapshot")
        return self


class DeclinedSession(SessionBase):
    kind: Literal["declined"]
    message: str = Field(min_length=1)
    rounds: list[RoundRecord] = Field(max_length=0)
    scoring: None = None
    judge: None = None


Session = Annotated[Union[CouncilSession, DeclinedSession], Field(discriminator="kind")]
_ADAPTER = TypeAdapter(Session)


def shape_problems(error: ValidationError) -> list[str]:
    """Pydantic's report as one line per problem: "rounds.0.turns.1.take_or_rebuttal.lean: Input should be ..."."""
    problems = []
    for item in error.errors():
        parts = [str(part) for part in item["loc"]]
        if parts and parts[0] in ("council", "declined"):
            parts = parts[1:]  # the union's tag for which kind of session was tried; it only gets in the way
        problems.append(f"{'.'.join(parts) or 'session'}: {item['msg']}")
    return problems


def final_replies(session: CouncilSession) -> dict[str, ReplyRecord]:
    """Each member's last good reply: the ones scoring used."""
    final = {}
    for round_ in session.rounds:
        for turn in round_.turns:
            if turn.status == "ok":
                final[turn.agent] = turn.take_or_rebuttal
    return final


def story_problems(session: CouncilSession) -> list[str]:
    """Does the session hang together? Rounds in order, one turn per member per round, and the scoring
    section matching the debate and the scoring rules."""
    problems = []

    numbers = [round_.number for round_ in session.rounds]
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append(f"rounds are numbered {numbers}; they must count 1, 2, 3 in order")
    kinds = [round_.kind for round_ in session.rounds]
    if kinds[0] != "opening" or kinds[1:2] not in ([], ["rebuttal"]) or any(kind != "tiebreak" for kind in kinds[2:]):
        problems.append(f"round kinds are {kinds}; they must be opening, then rebuttal, then tiebreaks")
    for round_ in session.rounds:
        names = [turn.agent for turn in round_.turns]
        repeats = sorted({name for name in names if names.count(name) > 1})
        if repeats:
            problems.append(f"round {round_.number}: {', '.join(repeats)} speaks more than once")

    final = final_replies(session)
    if len(final) < 2:
        problems.append(f"only {len(final)} member(s) gave a final answer; a verdict needs at least two")
        return problems

    result = session.scoring
    ratings = {agent: {name: rating.score for name, rating in reply.ratings.items()} for agent, reply in final.items()}
    if result.inputs != ratings:
        problems.append("scoring.inputs are not the ratings each member gave in its last turn")
    if result.leans is not None and result.leans != {agent: reply.lean for agent, reply in final.items()}:
        problems.append("scoring.leans are not the leans each member gave in its last turn")

    if result.formula_version == scoring.FORMULA_VERSION:
        recomputed = scoring.average_of(result.inputs)
        if recomputed != result.score:
            problems.append(f"the score is {result.score}, but its own ratings give {recomputed}")
        by_score = scoring.verdict_for(result.score)
        verdict, rail = scoring.apply_rails(by_score, list((result.leans or {}).values()))
        if result.score_verdict != by_score:
            problems.append(f"a score of {result.score} points to {by_score}, but the session says {result.score_verdict}")
        if (result.verdict, result.rail) != (verdict, rail):
            problems.append(f"this score and these leans give {verdict} (rail: {rail}), "
                            f"but the session says {result.verdict} (rail: {result.rail})")
        if result.verdict_label != scoring.VERDICT_LABELS[result.verdict]:
            problems.append(f"the label {result.verdict_label!r} does not match the verdict {result.verdict}")
    return problems


def check_session(data: object) -> list[str]:
    """Every problem with a session, in plain words. An empty list means the UI can read it."""
    if not isinstance(data, dict):
        return ["a session must be a JSON object"]
    version = data.get("schema_version")
    if version not in SUPPORTED_SCHEMAS:
        return [f"schema_version {version!r} is not supported; this code reads {', '.join(map(str, SUPPORTED_SCHEMAS))}"]
    try:
        session = _ADAPTER.validate_python(data)
    except ValidationError as error:
        return shape_problems(error)
    return story_problems(session) if isinstance(session, CouncilSession) else []


def parse_session(data: object) -> Union[CouncilSession, DeclinedSession]:
    problems = check_session(data)
    if problems:
        raise SessionError(problems)
    return _ADAPTER.validate_python(data)
