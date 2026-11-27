"""Input and output shapes for every agent (P2 <-> P3 <-> P4 contract).

Every agent returns one of the *Output models below, already validated.
P4's graph passes these objects between nodes; P5 logs them as JSON.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

UseCase = Literal["UC0", "UC1", "UC2", "UC3", "UC4", "UC5", "UC6", "UC7"]   # UC0 = small talk / help, no research
RefusalReason = Literal["advice_or_forecast", "out_of_scope", "not_in_context", "unsafe"]
UNITS = ("Rs crore", "Rs lakh", "Rs million", "%", "x", "count")
Unit = Literal["Rs crore", "Rs lakh", "Rs million", "%", "x", "count"]   # Analyst reports the unit as printed; P4 converts with unit_convert
DocType = Literal["annual_report", "quarterly_results", "press_release",
                  "investor_presentation", "call_transcript", "brsr", "other"]


# ============================================================ shared inputs
class Chunk(BaseModel):
    """One retrieved passage, as returned by P3's retrieve()."""
    chunk_id: str
    company: str
    fiscal_year: Optional[str] = None      # "FY24"
    quarter: Optional[str] = None          # "Q3"
    doc_type: Optional[str] = None
    doc: str                               # file name, e.g. "Dabur_AR_FY24.pdf"
    page: Optional[int] = None
    section: Optional[str] = None
    standalone_consolidated: Optional[str] = None   # "consolidated" | "standalone" | "unknown" (P3)
    source_id: Optional[str] = None                 # set by agents.py: the real chunk id behind a short E1..E5 id
    text: str
    score: Optional[float] = None


class ConversationState(BaseModel):
    """Carried across turns so follow-ups resolve ("and the year before?")."""
    last_companies: list[str] = []
    last_metrics: list[str] = []
    last_fiscal_years: list[str] = []
    last_use_case: Optional[UseCase] = None
    history: list[dict] = []               # [{"role": "user"|"assistant", "content": "..."}], last 4 turns


# ============================================================ Gatekeeper
class GateOutput(BaseModel):
    use_case: UseCase
    in_scope: bool
    refusal_reason: Optional[RefusalReason] = None
    refusal_message: Optional[str] = None  # shown to the user when in_scope is false
    companies: list[str] = []              # as the user named them; P4 resolves via company_lookup
    metrics: list[str] = []
    fiscal_years: list[str] = []           # "FY24"
    resolved_question: str                 # follow-ups rewritten as a standalone question
    direct_reply: Optional[str] = None     # UC0 only: the reply shown to the user; nothing is planned

    @field_validator("fiscal_years")
    @classmethod
    def fy_format(cls, v):
        for fy in v:
            if not (len(fy) == 4 and fy.startswith("FY") and fy[2:].isdigit()):
                raise ValueError(f"fiscal year '{fy}' must look like FY24")
        return v


# ============================================================ Planner
class SubTask(BaseModel):
    id: str                                # "t1", "t2", ...
    company: Optional[str] = None
    metric: Optional[str] = None           # "revenue from operations", "A&P spend", "EBITDA margin"
    fiscal_year: Optional[str] = None
    quarter: Optional[str] = None
    kind: Literal["lookup", "calculate", "commentary", "section"]
    question: str                          # one self-contained sub-question
    section: Optional[str] = None          # brief section name, only for kind="section"


class PlanOutput(BaseModel):
    subtasks: list[SubTask] = Field(min_length=1)
    combine: Literal["single_answer", "compare_rank", "summarise", "brief"]
    combine_instruction: str               # e.g. "rank companies by EBITDA margin, highest first"


# ============================================================ Query writer (Researcher)
class QueryFilters(BaseModel):
    company: Optional[str] = None
    fiscal_year: Optional[str] = None
    doc_type: Optional[DocType] = None


class QueryOutput(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=3)
    filters: QueryFilters


# ============================================================ Analyst
class ExtractedValue(BaseModel):
    label: str                             # "revenue from operations"
    value: float
    unit: Unit
    fiscal_year: Optional[str] = None
    chunk_id: str                          # must be one of the evidence chunk ids
    quote: str                             # exact text from the chunk containing the number


    @field_validator("unit", mode="before")
    @classmethod
    def _norm_unit(cls, v):
        return _coerce_unit(v)

class Calculation(BaseModel):
    expression: str                        # uses labels as variables, e.g. "a_p / revenue * 100"
    variables: dict[str, str]              # variable -> label of an ExtractedValue
    result_unit: Optional[Unit] = None     # unknown spellings become None; compute_result infers it (agents-v10)

    @field_validator("result_unit", mode="before")
    @classmethod
    def _norm_unit(cls, v):
        v = _coerce_unit(v)
        return v if v in UNITS else None


def _coerce_unit(v):
    """Map loose unit spellings ("Rs", "crores", "INR crore", "percent") to the allowed set."""
    if v is None:
        return v
    t = str(v).lower()
    if "%" in t or "percent" in t:
        return "%"
    if "lakh" in t:
        return "Rs lakh"
    if "million" in t or t.strip() in ("mn", "rs mn"):
        return "Rs million"
    if "crore" in t or t.strip() in ("rs", "inr", "rs.", "cr"):
        return "Rs crore"
    if t.strip() in ("times", "x"):
        return "x"
    return v


class AnalystOutput(BaseModel):
    values: list[ExtractedValue] = []
    calculation: Optional[Calculation] = None   # P4 runs it with the calculator tool
    missing: list[str] = []                # figures needed but not found in the evidence


# ============================================================ Writer
class Citation(BaseModel):
    chunk_id: str
    doc: Optional[str] = None              # filled in by code from the evidence chunk (agents-v2)
    page: Optional[int] = None             # filled in by code from the evidence chunk


class AnswerOutput(BaseModel):
    answer: str                            # 1-3 sentences, every number cited
    value: Optional[float] = None
    unit: Optional[Unit] = None
    fiscal_year: Optional[str] = None
    ranking: Optional[list[str]] = None
    citations: list[Citation] = []
    refused: bool = False
    refusal_reason: Optional[RefusalReason] = None


class SectionOutput(BaseModel):
    section: str                           # template section name
    text: str                              # <= 300 words, claims cited as [chunk_id]
    table: Optional[list[dict]] = None     # rows for the Snapshot / comparison tables
    citations: list[Citation] = []
    gaps: list[str] = []                   # what the evidence did not cover


# ============================================================ Critic
class CriticIssue(BaseModel):
    claim: str                             # the sentence or figure at fault
    quote: str                             # exact words copied from the draft text that are wrong (agents-v3)
    correct: str                           # what the correct value, unit, year or wording is
    problem: Literal["unsupported", "wrong_number", "wrong_unit", "wrong_fiscal_year",
                     "missing_citation", "incomplete", "answers_wrong_question", "unsafe"]
    fix_owner: Literal["researcher", "analyst", "writer"]
    instruction: str                       # what the owner must change

    @field_validator("problem", mode="before")
    @classmethod
    def _norm_problem(cls, v):
        """Map labels the 8B model invents ("misleading", "missing_data") to the allowed set (agents-v10.2)."""
        allowed = ("unsupported", "wrong_number", "wrong_unit", "wrong_fiscal_year", "missing_citation",
                   "incomplete", "answers_wrong_question", "unsafe")
        t = str(v or "").lower().strip()
        if t in allowed:
            return t
        for keys, label in ((("citation", "cite", "source"), "missing_citation"), (("unit", "crore", "lakh"), "wrong_unit"),
                            (("year", "fy", "period"), "wrong_fiscal_year"), (("number", "value", "figure", "calc"), "wrong_number"),
                            (("missing", "incomplete", "gap", "omit"), "incomplete"), (("question", "irrelevant"), "answers_wrong_question")):
            if any(k in t for k in keys):
                return label
        return "unsupported"

    @field_validator("fix_owner", mode="before")
    @classmethod
    def _norm_owner(cls, v):
        t = str(v or "").lower()
        return next((o for o in ("researcher", "analyst", "writer") if o in t), "writer")


class CriticOutput(BaseModel):
    verdict: Literal["pass", "revise"]
    issues: list[CriticIssue] = []
    verified: bool = True                  # False: the Critic's output was unusable; the draft is shown unverified (agents-v10.2)

    @field_validator("issues")
    @classmethod
    def issues_match_verdict(cls, v, info):
        if info.data.get("verdict") == "revise" and not v:
            raise ValueError("verdict 'revise' needs at least one issue")
        return v
