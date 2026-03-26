from __future__ import annotations

from pydantic import BaseModel
from app.agents.workers.market_scanner import MarketOpportunity


class EvaluationResult(BaseModel):
    top_opportunity: MarketOpportunity
    rationale: str


class OpportunityEvaluator:
    """Picks the best opportunity from a list using a scoring heuristic.

    No LLM needed — pure logic. Higher confidence_score wins; ties broken by
    higher estimated_arr. Builds a rationale string explaining the choice.
    """

    async def evaluate(self, opportunities: list[MarketOpportunity]) -> EvaluationResult:
        best = max(
            opportunities,
            key=lambda o: (o.confidence_score, o.estimated_arr),
        )
        rationale = (
            f"Selected '{best.name}' with confidence {best.confidence_score:.0%} "
            f"and estimated ARR ${best.estimated_arr:,.0f}. "
            f"Competition level: {best.competition_level}."
        )
        return EvaluationResult(top_opportunity=best, rationale=rationale)
