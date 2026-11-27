"""Shared response model for backends, services, and persistence."""

from dataclasses import dataclass, field

@dataclass
class ChatResponse:
    answer: str
    citations: list[dict] = field(default_factory=list)
    successful: bool = True
    cacheable: bool = False
    status: str = "answered"
    results: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    agent_context: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    sections: list[dict] = field(default_factory=list)
