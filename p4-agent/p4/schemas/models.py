from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict

Status = Literal["answered", "partial", "clarification_needed", "refused", "not_found"]
Basis = Literal["consolidated", "standalone", "segment", "not_stated"]

class Citation(BaseModel):
    company: str
    document: str
    page: int = Field(ge=1)
    quote_or_locator: Optional[str] = None
    source_id: Optional[str] = None

class ResultItem(BaseModel):
    company: str
    metric: str
    source_metric: Optional[str] = None
    value: Optional[float] = None
    unit: str
    period: str
    basis: Basis
    formula: Optional[str] = None
    citations: list[Citation] = Field(default_factory=list)

class CopilotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status
    use_case: Optional[str] = None
    answer: str
    results: list[ResultItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    follow_up: Optional[str] = None
    refusal_code: Optional[str] = None

class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

class PlanStep(BaseModel):
    task_id: str
    task: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)

class Subtask(BaseModel):
    task_id: str
    objective: str
    company: Optional[str] = None
    metric: Optional[str] = None
    period: Optional[str] = None
    basis: Optional[str] = None
    retrieval_query: Optional[str] = None
    tool_steps: list[PlanStep] = Field(default_factory=list)

class Plan(BaseModel):
    use_case: str
    steps: list[PlanStep] = Field(default_factory=list)
    subtasks: list[Subtask] = Field(default_factory=list)
