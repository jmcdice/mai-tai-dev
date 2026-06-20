"""WhatsApp bridge — glue between Evolution API and mai-tai workspaces.

Two directions:
  inbound:  Evolution webhook  -> parse_inbound() -> Message(channel="wa") in a workspace
  outbound: agent send_to_wa   -> send_text()     -> Evolution REST -> WhatsApp

The agent only ever reaches WhatsApp through `channel="wa"` messages, so a
workspace's private (web-UI) conversation never leaks to the group.

STATUS: scaffold. The Evolution webhook payload parsing (parse_inbound) is
written defensively but MUST be validated against real Evolution v2 payloads
before relying on it — see TODOs.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from app.core.config import get_settings

# message_metadata channel values
CHANNEL_PRIVATE = "private"
CHANNEL_WA = "wa"


def _evolution_headers() -> dict[str, str]:
    settings = get_settings()
    return {"apikey": settings.evolution_api_key, "Content-Type": "application/json"}


async def send_text(instance: str, to_jid: str, text: str) -> dict[str, Any]:
    """Send a text message to a WhatsApp chat (group or individual) via Evolution.

    Args:
        instance: Evolution instance name (the linked number).
        to_jid:   Target chat JID — a group id (e.g. "...@g.us") or a user
                  number/JID (e.g. "5511...@s.whatsapp.net" or bare number).
        text:     Message body.
    """
    settings = get_settings()
    url = f"{settings.evolution_base_url}/message/sendText/{instance}"
    payload = {"number": to_jid, "text": text}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=_evolution_headers())
        resp.raise_for_status()
        return resp.json()


def parse_inbound(event: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize an Evolution `messages.upsert` webhook into bridge fields.

    Returns a dict with:
        instance, wa_message_id, chat_jid, sender_jid, wa_name, wa_number,
        text, is_group, mentioned_jids, from_me
    or None if the event isn't a usable inbound text message.

    TODO(verify): confirm these paths against a real Evolution v2 payload. The
    shape below follows the documented `data.key` / `data.message` structure but
    field names drift between versions.
    """
    if event.get("event") not in ("messages.upsert", "MESSAGES_UPSERT"):
        return None

    data = event.get("data") or {}
    key = data.get("key") or {}
    message = data.get("message") or {}

    from_me = bool(key.get("fromMe"))
    chat_jid = key.get("remoteJid") or ""
    is_group = chat_jid.endswith("@g.us")

    # Text can live in a few places depending on message type.
    text = (
        message.get("conversation")
        or (message.get("extendedTextMessage") or {}).get("text")
        or ""
    )
    if not text:
        return None

    # In a group, the actual sender is `participant`; in a DM it's the chat jid.
    sender_jid = key.get("participant") or chat_jid
    wa_number = sender_jid.split("@", 1)[0].split(":", 1)[0] if sender_jid else ""

    # @-mentions: list of mentioned JIDs (Evolution puts these in contextInfo).
    context = (message.get("extendedTextMessage") or {}).get("contextInfo") or {}
    mentioned_jids = context.get("mentionedJid") or []

    return {
        "instance": event.get("instance") or data.get("instanceName") or "",
        "wa_message_id": key.get("id") or "",
        "chat_jid": chat_jid,
        "sender_jid": sender_jid,
        "wa_name": data.get("pushName") or wa_number,
        "wa_number": wa_number,
        "text": text,
        "is_group": is_group,
        "mentioned_jids": mentioned_jids,
        "from_me": from_me,
    }


def is_agent_mentioned(parsed: dict[str, Any], bot_jid: str | None) -> bool:
    """True if the bot was @-mentioned in the message.

    If `bot_jid` is unknown (not yet configured), fall back to False so the
    bridge stays quiet rather than replying to everything.
    """
    if not bot_jid:
        return False
    return any(bot_jid.split("@", 1)[0] in m for m in parsed.get("mentioned_jids", []))


def wa_message_metadata(parsed: dict[str, Any]) -> dict[str, Any]:
    """Build message_metadata for an inbound WhatsApp message."""
    return {
        "source": "whatsapp",
        "channel": CHANNEL_WA,
        "wa_name": parsed["wa_name"],
        "wa_number": parsed["wa_number"],
        "wa_message_id": parsed["wa_message_id"],
        "wa_chat_jid": parsed["chat_jid"],
        "wa_is_group": parsed["is_group"],
    }


def workspace_wa_config(workspace) -> dict[str, Any]:
    """Read a workspace's WhatsApp binding from agent_config.

    Expected shape in Workspace.agent_config:
        {"whatsapp": {"instance": "...", "target_jid": "...@g.us",
                      "bot_jid": "...@s.whatsapp.net", "mention_required": true}}
    """
    cfg = (workspace.agent_config or {}).get("whatsapp") or {}
    return {
        "instance": cfg.get("instance"),
        "target_jid": cfg.get("target_jid"),
        "bot_jid": cfg.get("bot_jid"),
        "mention_required": cfg.get("mention_required", True),
    }
