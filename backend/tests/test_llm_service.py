# backend/tests/test_llm_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import BaseModel
from app.services.llm import LLMService


class DummyOutput(BaseModel):
    name: str
    score: float


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock()
    return client


@pytest.fixture
def llm(mock_client):
    svc = LLMService(client=mock_client, model="claude-haiku-4-5-20251001")
    return svc


@pytest.mark.asyncio
async def test_call_returns_parsed_model(llm, mock_client):
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"name": "B2B invoicing", "score": 0.9}')],
        usage=MagicMock(input_tokens=100, output_tokens=50),
    )
    result = await llm.call(
        system="You are a market analyst.",
        prompt="Evaluate this opportunity.",
        output_schema=DummyOutput,
    )
    assert isinstance(result, DummyOutput)
    assert result.name == "B2B invoicing"
    assert result.score == 0.9


@pytest.mark.asyncio
async def test_call_retries_on_validation_error(llm, mock_client):
    bad = MagicMock(
        content=[MagicMock(text="not json at all")],
        usage=MagicMock(input_tokens=10, output_tokens=5),
    )
    good = MagicMock(
        content=[MagicMock(text='{"name": "SaaS", "score": 0.7}')],
        usage=MagicMock(input_tokens=10, output_tokens=10),
    )
    mock_client.messages.create.side_effect = [bad, good]
    result = await llm.call(
        system="You are a market analyst.",
        prompt="Evaluate.",
        output_schema=DummyOutput,
    )
    assert isinstance(result, DummyOutput)
    assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_call_raises_after_max_retries(llm, mock_client):
    bad = MagicMock(
        content=[MagicMock(text="not json")],
        usage=MagicMock(input_tokens=10, output_tokens=5),
    )
    mock_client.messages.create.return_value = bad
    with pytest.raises(ValueError, match="LLM failed to return valid"):
        await llm.call(
            system="You are a market analyst.",
            prompt="Evaluate.",
            output_schema=DummyOutput,
            max_retries=3,
        )
    assert mock_client.messages.create.call_count == 3


@pytest.mark.asyncio
async def test_call_tracks_token_usage(llm, mock_client):
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"name": "SaaS", "score": 0.5}')],
        usage=MagicMock(input_tokens=200, output_tokens=100),
    )
    await llm.call(
        system="sys",
        prompt="prompt",
        output_schema=DummyOutput,
    )
    assert llm.total_input_tokens == 200
    assert llm.total_output_tokens == 100
