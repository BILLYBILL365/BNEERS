from __future__ import annotations

from pydantic import BaseModel
from app.services.llm import LLMService


class MarketOpportunity(BaseModel):
    name: str
    description: str
    target_market: str
    estimated_arr: float
    competition_level: str  # "low" | "medium" | "high"
    confidence_score: float  # 0.0 – 1.0


class MarketScanResult(BaseModel):
    opportunities: list[MarketOpportunity]
    reasoning: str


SYSTEM_PROMPT = """You are a SaaS market research analyst.
Your job is to identify high-potential SaaS opportunities with clear demand and revenue potential.
Focus on B2B markets with recurring revenue potential.
Be specific and data-driven in your assessments."""

SCAN_PROMPT = """Identify 3–5 promising SaaS market opportunities right now.
For each opportunity provide: name, description, target_market, estimated_arr (USD),
competition_level (low/medium/high), and a confidence_score (0.0–1.0).
Also provide reasoning for your selections."""


class MarketScanner:
    """Calls LLM to identify SaaS market opportunities."""

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    async def scan(self) -> MarketScanResult:
        return await self._llm.call(
            system=SYSTEM_PROMPT,
            prompt=SCAN_PROMPT,
            output_schema=MarketScanResult,
        )
