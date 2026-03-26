"""
Tests for DiscordNotifier: config, routing, button handlers, and bus integration.
"""
import pytest
import httpx
import fakeredis.aioredis as fakeredis
from unittest.mock import AsyncMock, MagicMock
from app.config import Settings
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent
from app.services.discord_notifier import DiscordNotifier, ApprovalView


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_notifier(approvals_id=111, updates_id=222, alerts_id=333):
    """Build a DiscordNotifier with a fully-mocked discord client."""
    mock_client = MagicMock()
    mock_http = AsyncMock()
    notifier = DiscordNotifier(
        bot_token="fake-token",
        approvals_channel_id=approvals_id,
        updates_channel_id=updates_id,
        alerts_channel_id=alerts_id,
        client=mock_client,
        http=mock_http,
        backend_base_url="http://localhost:8000",
    )
    return notifier, mock_client, mock_http


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

def test_discord_config_fields_have_defaults():
    s = Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379",
        SECRET_KEY="test-secret",
    )
    assert s.DISCORD_BOT_TOKEN == ""
    assert s.DISCORD_APPROVALS_CHANNEL_ID == 0
    assert s.DISCORD_UPDATES_CHANNEL_ID == 0
    assert s.DISCORD_ALERTS_CHANNEL_ID == 0
    assert s.DISCORD_BACKEND_URL == "http://localhost:8000"


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decision_pending_routes_to_approvals():
    notifier, mock_client, _ = _make_notifier()
    mock_channel = AsyncMock()
    mock_client.get_channel.return_value = mock_channel

    await notifier.handle_event(BusEvent(
        type="decision.pending",
        payload={"decision_id": "abc123", "title": "Enter B2B market", "description": "Strong demand"},
    ))

    mock_client.get_channel.assert_called_with(111)
    mock_channel.send.assert_called_once()
    _, kwargs = mock_channel.send.call_args
    assert "embed" in kwargs
    assert "view" in kwargs


@pytest.mark.asyncio
async def test_agent_alert_routes_to_alerts():
    notifier, mock_client, _ = _make_notifier()
    mock_channel = AsyncMock()
    mock_client.get_channel.return_value = mock_channel

    await notifier.handle_event(BusEvent(
        type="agent.alert",
        payload={"agent_id": "cso", "reason": "heartbeat_overdue"},
    ))

    mock_client.get_channel.assert_called_with(333)
    mock_channel.send.assert_called_once()


@pytest.mark.asyncio
async def test_spend_exceeded_routes_to_alerts():
    notifier, mock_client, _ = _make_notifier()
    mock_channel = AsyncMock()
    mock_client.get_channel.return_value = mock_channel

    await notifier.handle_event(BusEvent(
        type="spend.exceeded",
        payload={"category": "ads", "daily_total": 105.0, "cap": 100.0},
    ))

    mock_client.get_channel.assert_called_with(333)
    mock_channel.send.assert_called_once()


@pytest.mark.asyncio
async def test_decision_approved_routes_to_updates():
    notifier, mock_client, _ = _make_notifier()
    mock_channel = AsyncMock()
    mock_client.get_channel.return_value = mock_channel

    await notifier.handle_event(BusEvent(
        type="decision.approved",
        payload={"decision_id": "abc123", "title": "Enter B2B market", "decided_by": "board"},
    ))

    mock_client.get_channel.assert_called_with(222)
    mock_channel.send.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_event_is_ignored():
    notifier, mock_client, _ = _make_notifier()
    await notifier.handle_event(BusEvent(type="some.unknown.event", payload={}))
    mock_client.get_channel.assert_not_called()


@pytest.mark.asyncio
async def test_no_client_handle_event_is_noop():
    """When client is None (bot token not set), handle_event returns immediately."""
    notifier = DiscordNotifier(
        bot_token="",
        approvals_channel_id=111,
        updates_channel_id=222,
        alerts_channel_id=333,
        client=None,
        http=None,
        backend_base_url="http://localhost:8000",
    )
    assert notifier._client is None  # bot_token="" means no client was created
    await notifier.handle_event(BusEvent(
        type="decision.pending",
        payload={"decision_id": "x", "title": "T", "description": "D"},
    ))
    # If the guard didn't fire, AttributeError on None.get_channel() would have raised above.
    # Explicit state assertion: _client unchanged confirms no side effects occurred.
    assert notifier._client is None


# ---------------------------------------------------------------------------
# ApprovalView button tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_button_calls_approve_endpoint():
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=MagicMock(status_code=200))

    view = ApprovalView(
        decision_id="abc123",
        http=mock_http,
        base_url="http://localhost:8000",
    )

    mock_interaction = AsyncMock()
    mock_interaction.response = AsyncMock()

    await ApprovalView.__dict__["approve"](view, mock_interaction, MagicMock())

    mock_http.post.assert_called_once_with("http://localhost:8000/decisions/abc123/approve")
    mock_interaction.response.send_message.assert_called_once_with("Decision approved.", ephemeral=True)


@pytest.mark.asyncio
async def test_reject_button_calls_reject_endpoint():
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=MagicMock(status_code=200))

    view = ApprovalView(
        decision_id="xyz789",
        http=mock_http,
        base_url="http://localhost:8000",
    )

    mock_interaction = AsyncMock()
    mock_interaction.response = AsyncMock()

    await ApprovalView.__dict__["reject"](view, mock_interaction, MagicMock())

    mock_http.post.assert_called_once_with("http://localhost:8000/decisions/xyz789/reject")
    mock_interaction.response.send_message.assert_called_once_with("Decision rejected.", ephemeral=True)


@pytest.mark.asyncio
async def test_approve_button_handles_http_error():
    """On transient HTTP failure the view stays active (no self.stop()) and sends error message."""
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    view = ApprovalView(
        decision_id="abc123",
        http=mock_http,
        base_url="http://localhost:8000",
    )

    mock_interaction = AsyncMock()
    mock_interaction.response = AsyncMock()

    # Should not raise
    await ApprovalView.__dict__["approve"](view, mock_interaction, MagicMock())

    # Handler ran: error message was sent to the user
    mock_interaction.response.send_message.assert_called_once()
    _, kwargs = mock_interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    msg = mock_interaction.response.send_message.call_args[0][0]
    assert "Error" in msg
    # stop() was NOT called on error — board member can retry
    assert not view.is_finished()


# ---------------------------------------------------------------------------
# Bus integration test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bus_to_discord_routing():
    """Fire bus events through RedisBus, verify notifier sends to correct channels."""
    redis = fakeredis.FakeRedis()
    bus = RedisBus(redis_client=redis)

    approvals_channel = AsyncMock()
    updates_channel = AsyncMock()
    alerts_channel = AsyncMock()

    def get_channel(channel_id):
        return {111: approvals_channel, 222: updates_channel, 333: alerts_channel}.get(channel_id)

    mock_client = MagicMock()
    mock_client.get_channel = MagicMock(side_effect=get_channel)

    notifier = DiscordNotifier(
        bot_token="fake",
        approvals_channel_id=111,
        updates_channel_id=222,
        alerts_channel_id=333,
        client=mock_client,
        http=AsyncMock(),
        backend_base_url="http://localhost:8000",
    )

    for event_type in ("decision.pending", "decision.approved", "agent.alert", "spend.exceeded"):
        await bus.subscribe(event_type, notifier.handle_event)

    await bus.publish(BusEvent(type="decision.pending", payload={"decision_id": "d1", "title": "Big move", "description": "Go big"}))
    await bus.publish(BusEvent(type="decision.approved", payload={"decision_id": "d1", "title": "Big move", "decided_by": "board"}))
    await bus.publish(BusEvent(type="agent.alert", payload={"agent_id": "cso", "reason": "heartbeat_overdue"}))
    await bus.publish(BusEvent(type="spend.exceeded", payload={"category": "ads", "daily_total": 110.0, "cap": 100.0}))

    # Drain bus until empty
    for _ in range(20):
        if not await bus.process_one():
            break

    assert approvals_channel.send.call_count == 1   # decision.pending
    assert updates_channel.send.call_count == 1      # decision.approved
    assert alerts_channel.send.call_count == 2       # agent.alert + spend.exceeded


def test_discord_notifier_import_and_instantiation():
    """Smoke test: DiscordNotifier can be instantiated with empty token (no-op mode)."""
    notifier = DiscordNotifier(
        bot_token="",
        approvals_channel_id=0,
        updates_channel_id=0,
        alerts_channel_id=0,
    )
    assert notifier._client is None
    assert notifier._http is None
