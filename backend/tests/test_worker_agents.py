import pytest
from unittest.mock import AsyncMock, MagicMock
from app.agents.workers.market_scanner import MarketScanner, MarketScanResult, MarketOpportunity
from app.agents.workers.opportunity_evaluator import OpportunityEvaluator, EvaluationResult
from app.agents.workers.code_writer import CodeWriter, CodeScaffold
from app.agents.workers.qa_tester import QATester, TestPlan
from app.agents.workers.devops import DevOps, DeploymentConfig
from app.agents.workers.content_writer import ContentWriter, ContentPackage
from app.agents.workers.ad_manager import AdManager, AdCopy
from app.agents.workers.social_media import SocialMedia, SocialPosts


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


@pytest.mark.asyncio
async def test_code_writer_returns_scaffold():
    scaffold = CodeScaffold(
        project_structure=["src/main.py", "src/models.py"],
        main_code="# main entry point\n",
        dependencies=["fastapi", "sqlalchemy"],
        setup_instructions="pip install -r requirements.txt",
    )
    llm = make_llm(scaffold)
    writer = CodeWriter(llm=llm)
    result = await writer.write(
        product_name="B2B Invoicing",
        product_description="Automated invoicing SaaS",
    )
    assert isinstance(result, CodeScaffold)
    assert "fastapi" in result.dependencies
    llm.call.assert_called_once()


@pytest.mark.asyncio
async def test_qa_tester_returns_test_plan():
    plan = TestPlan(
        test_cases=["test_create_invoice", "test_send_invoice"],
        testing_framework="pytest",
        coverage_target=80,
    )
    llm = make_llm(plan)
    tester = QATester(llm=llm)
    result = await tester.create_plan(
        product_name="B2B Invoicing",
        code_files=["src/main.py"],
    )
    assert isinstance(result, TestPlan)
    assert result.coverage_target == 80


@pytest.mark.asyncio
async def test_devops_returns_deployment_config():
    config = DeploymentConfig(
        dockerfile="FROM python:3.12\n...",
        railway_config={"build": {"builder": "dockerfile"}},
        environment_variables=["DATABASE_URL", "REDIS_URL"],
        deploy_steps=["build", "migrate", "start"],
    )
    llm = make_llm(config)
    devops = DevOps(llm=llm)
    result = await devops.create_config(product_name="B2B Invoicing")
    assert isinstance(result, DeploymentConfig)
    assert "DATABASE_URL" in result.environment_variables


@pytest.mark.asyncio
async def test_content_writer_returns_package():
    pkg = ContentPackage(
        landing_page_headline="Invoice faster, get paid sooner",
        landing_page_body="10 sentences of copy...",
        blog_post_titles=["5 ways to reduce late payments"],
        email_subject="Stop chasing invoices",
    )
    llm = make_llm(pkg)
    writer = ContentWriter(llm=llm)
    result = await writer.create(product_name="B2B Invoicing", target_market="SMB")
    assert isinstance(result, ContentPackage)
    assert result.email_subject != ""


@pytest.mark.asyncio
async def test_ad_manager_returns_ad_copy():
    copy = AdCopy(
        headline="Automate your invoicing",
        body="Never chase a payment again.",
        cta="Start free trial",
        estimated_cpc=2.50,
    )
    llm = make_llm(copy)
    mgr = AdManager(llm=llm)
    result = await mgr.create_ad(product_name="B2B Invoicing", budget=50.0)
    assert isinstance(result, AdCopy)
    assert result.estimated_cpc > 0


@pytest.mark.asyncio
async def test_social_media_returns_posts():
    posts = SocialPosts(
        twitter=["Check out our new invoicing tool! #SaaS"],
        linkedin=["We just launched B2B Invoicing..."],
    )
    llm = make_llm(posts)
    social = SocialMedia(llm=llm)
    result = await social.create_posts(product_name="B2B Invoicing")
    assert isinstance(result, SocialPosts)
    assert len(result.twitter) > 0
