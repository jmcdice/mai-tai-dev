"""WhatsApp bridge endpoints — inbound webhook from Evolution API.

Evolution POSTs WhatsApp events here. We:
  1. verify the shared secret,
  2. resolve the Evolution instance -> mai-tai workspace,
  3. (optionally) require the bot to be @-mentioned,
  4. write the message into the workspace as channel="wa",
  5. broadcast to web-UI websocket clients.

The agent then picks it up via its normal MCP polling loop and may reply with
`send_to_wa` (which routes back out through wa_bridge.send_text).

STATUS: scaffold. Validate against real Evolution payloads before production.
"""

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.websocket import manager as ws_manager
from app.models.message import Message
from app.models.workspace import Workspace
from app.services import wa_bridge

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.post("/webhook")
async def evolution_webhook(
    request: Request,
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive an Evolution API webhook event."""
    settings = get_settings()

    # 1. Verify shared secret (accepted via query param OR X-Webhook-Secret header).
    expected = settings.wa_webhook_secret
    header_secret = request.headers.get("x-webhook-secret", "")
    if not expected or (secret != expected and header_secret != expected):
        return {"status": "unauthorized"}

    event = await request.json()
    parsed = wa_bridge.parse_inbound(event)
    if not parsed or parsed["from_me"]:
        # Not a usable inbound text, or it's our own echo — ignore.
        return {"status": "ignored"}

    # 2. Resolve instance -> workspace via agent_config->whatsapp->instance.
    instance = parsed["instance"]
    result = await db.execute(
        select(Workspace).where(
            Workspace.agent_config["whatsapp"]["instance"].astext == instance
        )
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        return {"status": "no_workspace", "instance": instance}

    cfg = wa_bridge.workspace_wa_config(workspace)

    # 3. Mention gate (default on): only act when the bot is @-mentioned.
    if cfg["mention_required"] and not wa_bridge.is_agent_mentioned(parsed, cfg["bot_jid"]):
        return {"status": "no_mention"}

    # 4. Dedupe by wa_message_id, then persist as a channel="wa" message.
    wa_msg_id = parsed["wa_message_id"]
    if wa_msg_id:
        dupe = await db.execute(
            select(Message.id).where(
                Message.workspace_id == workspace.id,
                Message.message_metadata["wa_message_id"].astext == wa_msg_id,
            )
        )
        if dupe.first() is not None:
            return {"status": "duplicate"}

    metadata = wa_bridge.wa_message_metadata(parsed)
    # Prefix sender name so the agent immediately knows who/where, mirroring the
    # MCP convention of "[Name]: ..." for multi-human context.
    content = f"[{parsed['wa_name']} via WhatsApp]: {parsed['text']}"

    message = Message(
        workspace_id=workspace.id,
        user_id=None,
        agent_name=None,
        content=content,
        message_metadata=metadata,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    # 5. Broadcast to web-UI clients so the owner sees the group chatter live.
    await ws_manager.broadcast_to_channel(str(workspace.id), {
        "type": "new_message",
        "message": {
            "id": str(message.id),
            "workspace_id": str(message.workspace_id),
            "user_id": None,
            "agent_name": None,
            "sender_name": parsed["wa_name"],
            "content": message.content,
            "message_metadata": message.message_metadata,
            "created_at": message.created_at.isoformat(),
            "message_type": message.message_type,
        },
    })

    return {"status": "ok", "message_id": str(message.id)}
