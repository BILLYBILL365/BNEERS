from __future__ import annotations

import asyncio
from typing import Any

import discord
import httpx

from app.schemas.events import BusEvent

_APPROVALS_EVENTS = {"decision.pending"}
_UPDATES_EVENTS = {"decision.approved", "decision.rejected", "task.created", "task.completed", "agent.status"}
_ALERTS_EVENTS = {"agent.alert", "spend.exceeded"}


class ApprovalView(discord.ui.View):
    """Approve / Reject buttons for a pending decision.

    Uses timeout=300 (non-persistent) so discord.py routes each interaction
    to the correct view instance — no globally-unique custom_id required.
    view.stop() is called on success only; on HTTP error the buttons remain
    active so the board member can retry.
    """

    def __init__(self, decision_id: str, http: httpx.AsyncClient, base_url: str) -> None:
        super().__init__(timeout=300)
        self._decision_id = decision_id
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            await self._http.post(f"{self._base_url}/decisions/{self._decision_id}/approve")
            await interaction.response.send_message("Decision approved.", ephemeral=True)
            self.stop()
        except Exception as exc:  # noqa: BLE001
            await interaction.response.send_message(f"Error: {exc}", ephemeral=True)

    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            await self._http.post(f"{self._base_url}/decisions/{self._decision_id}/reject")
            await interaction.response.send_message("Decision rejected.", ephemeral=True)
            self.stop()
        except Exception as exc:  # noqa: BLE001
            await interaction.response.send_message(f"Error: {exc}", ephemeral=True)


# Apply button decorators to the methods for Discord UI registration
ApprovalView.approve = discord.ui.button(label="Approve", style=discord.ButtonStyle.green)(ApprovalView.approve)
ApprovalView.reject = discord.ui.button(label="Reject", style=discord.ButtonStyle.red)(ApprovalView.reject)


class DiscordNotifier:
    """Subscribes to bus events and sends messages to Discord channels."""

    def __init__(
        self,
        bot_token: str,
        approvals_channel_id: int,
        updates_channel_id: int,
        alerts_channel_id: int,
        backend_base_url: str = "http://localhost:8000",
        client: Any | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = bot_token
        self._channel_ids = {
            "approvals": approvals_channel_id,
            "updates": updates_channel_id,
            "alerts": alerts_channel_id,
        }
        self._base_url = backend_base_url.rstrip("/")
        self._http = http or (httpx.AsyncClient() if bot_token else None)
        self._client: discord.Client | Any | None = client
        self._bot_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the Discord bot. No-op if bot token is empty."""
        if not self._token:
            return
        if self._client is None:
            intents = discord.Intents.default()
            self._client = discord.Client(intents=intents)

        ready = asyncio.Event()

        @self._client.event
        async def on_ready() -> None:
            ready.set()

        self._bot_task = asyncio.create_task(self._client.start(self._token))
        try:
            await asyncio.wait_for(ready.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass

    async def stop(self) -> None:
        if self._client and hasattr(self._client, "close"):
            await self._client.close()
        if self._bot_task:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass
        if self._http:
            await self._http.aclose()

    async def handle_event(self, event: BusEvent) -> None:
        if self._client is None:
            return
        if event.type in _APPROVALS_EVENTS:
            await self._send_approval_request(event.payload)
        elif event.type in _UPDATES_EVENTS:
            await self._send_update(event)
        elif event.type in _ALERTS_EVENTS:
            await self._send_alert(event)

    async def _send_approval_request(self, payload: dict) -> None:
        channel = self._client.get_channel(self._channel_ids["approvals"])
        if channel is None:
            return
        embed = discord.Embed(
            title=f"Decision Request: {payload.get('title', 'Untitled')}",
            description=payload.get("description", ""),
            color=discord.Color.orange(),
        )
        embed.add_field(name="Decision ID", value=payload.get("decision_id", ""), inline=False)
        embed.add_field(name="Requested by", value=payload.get("requested_by", "agent"), inline=True)
        view = ApprovalView(
            decision_id=payload["decision_id"],
            http=self._http,
            base_url=self._base_url,
        )
        await channel.send(embed=embed, view=view)

    async def _send_update(self, event: BusEvent) -> None:
        channel = self._client.get_channel(self._channel_ids["updates"])
        if channel is None:
            return
        await channel.send(_format_update(event))

    async def _send_alert(self, event: BusEvent) -> None:
        channel = self._client.get_channel(self._channel_ids["alerts"])
        if channel is None:
            return
        await channel.send(_format_alert(event))


def _format_update(event: BusEvent) -> str:
    p = event.payload
    if event.type == "decision.approved":
        return f"Board approved: **{p.get('title', p.get('decision_id', ''))}**"
    if event.type == "decision.rejected":
        return f"Board rejected: **{p.get('title', p.get('decision_id', ''))}**"
    if event.type == "task.created":
        return f"New task created: `{p.get('task_id', '')}` — {p.get('title', '')}"
    if event.type == "task.completed":
        return f"Task completed: `{p.get('task_id', '')}` — {p.get('title', '')}"
    if event.type == "agent.status":
        return f"Agent `{p.get('agent_id', '')}` is now **{p.get('status', '')}**"
    return f"[{event.type}] {p}"


def _format_alert(event: BusEvent) -> str:
    p = event.payload
    if event.type == "agent.alert":
        return f"ALERT: Agent `{p.get('agent_id', '')}` — {p.get('reason', 'unknown reason')}"
    if event.type == "spend.exceeded":
        return (
            f"SPEND ALERT: `{p.get('category', '')}` daily cap exceeded. "
            f"Spent: ${p.get('daily_total', 0):.2f} / Cap: ${p.get('cap', 0):.2f}"
        )
    return f"[ALERT] [{event.type}] {p}"
