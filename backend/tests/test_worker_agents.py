import pytest
from unittest.mock import AsyncMock, MagicMock
from app.agents.workers.market_scanner import MarketScanner, MarketScanResult, MarketOpportunity
from app.agents.workers.opportunity_evaluator import OpportunityEvaluator, EvaluationResult


def make_llm(return_value):
    llm = MagicMock()
    llm.call = AsyncMock(return_value=return_value)
    return llm


@pytest.mark.asyncio
async def test_market_scanner_returns_opportunities():
    opportunities = [
        MarketOpportunity(
            name="B2B Invoicing SaaS",
            description="Automated invoicing for small businesses",
            target_market="SMB",
            estimated_arr=500_000.0,
            competition_level="medium",
            confidence_score=0.85,
        )
    ]
    llm = make_llm(MarketScanResult(opportunities=opportunities, reasoning="Strong demand"))
    scanner = MarketScanner(llm=llm)
    result = await scanner.scan()
    assert isinstance(result, MarketScanResult)
    assert len(result.opportunities) == 1
    assert result.opportunities[0].name == "B2B Invoicing SaaS"
    llm.call.assert_called_once()


@pytest.mark.asyncio
async def test_opportunity_evaluator_picks_highest_confidence():
    opps = [
        MarketOpportunity(
            name="Low confidence opp",
            description="Meh",
            target_market="SMB",
            estimated_arr=100_000.0,
            competition_level="high",
            confidence_score=0.4,
        ),
        MarketOpportunity(
            name="High confidence opp",
            description="Great",
            target_market="Enterprise",
            estimated_arr=2_000_000.0,
            competition_level="low",
            confidence_score=0.92,
        ),
    ]
    evaluator = OpportunityEvaluator()
    result = await evaluator.evaluate(opps)
    assert isinstance(result, EvaluationResult)
    assert result.top_opportunity.name == "High confidence opp"
    assert result.rationale != ""


@pytest.mark.asyncio
async def test_opportunity_evaluator_handles_single_opportunity():
    opps = [
        MarketOpportunity(
            name="Only option",
            description="desc",
            target_market="SMB",
            estimated_arr=300_000.0,
            competition_level="low",
            confidence_score=0.7,
        )
    ]
    evaluator = OpportunityEvaluator()
    result = await evaluator.evaluate(opps)
    assert result.top_opportunity.name == "Only option"
