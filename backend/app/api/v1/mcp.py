"""MCP API endpoints - authenticated via API key for external coding agents."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApiKeyAuth, get_api_key_auth, get_db
from app.core.websocket import manager as ws_manager
from app.models.message import Message
from app.models.user import User
from app.schemas.message import (
    MessageAcknowledgeRequest,
    MessageAcknowledgeResponse,
    MessageCreate,
    MessageListResponse,
    MessageResponse,
)
from app.schemas.workspace import WorkspaceResponse

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/auth/verify")
async def verify_api_key(
    auth: ApiKeyAuth = Depends(get_api_key_auth),
) -> dict:
    """Verify API key and return workspace info."""
    return {
        "status": "authenticated",
        "workspace_id": str(auth.workspace_id),
        "workspace_name": auth.workspace.name,
        "api_key_name": auth.api_key.name,
    }


@router.get("/workspace", response_model=WorkspaceResponse)
async def get_workspace(
    auth: ApiKeyAuth = Depends(get_api_key_auth),
) -> dict:
    """Get the workspace this API key is bound to."""
    return auth.workspace


@router.post(
    "/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    data: MessageCreate,
    auth: ApiKeyAuth = Depends(get_api_key_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send a message to the workspace (from MCP agent)."""
    message = Message(
        workspace_id=auth.workspace_id,
        user_id=None,  # MCP agents don't have a user ID
        agent_name=auth.api_key.name,  # Use API key name as agent name
        content=data.content,
        message_metadata=data.metadata or {"source": "mcp", "api_key": auth.api_key.name},
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    # Broadcast to WebSocket clients
    await ws_manager.broadcast_to_channel(str(auth.workspace_id), {
        "type": "new_message",
        "message": {
            "id": str(message.id),
            "workspace_id": str(message.workspace_id),
            "user_id": None,
            "agent_name": message.agent_name,
            "sender_name": message.agent_name,
            "content": message.content,
            "message_metadata": message.message_metadata,
            "created_at": message.created_at.isoformat(),
            "message_type": message.message_type,
        },
    })

    return {
        "id": message.id,
        "workspace_id": message.workspace_id,
        "user_id": None,
        "agent_name": message.agent_name,
        "sender_name": message.agent_name,
        "content": message.content,
        "message_metadata": message.message_metadata,
        "created_at": message.created_at,
        "message_type": message.message_type,
    }


@router.post(
    "/messages/acknowledge",
    response_model=MessageAcknowledgeResponse,
)
async def acknowledge_messages(
    data: MessageAcknowledgeRequest,
    auth: ApiKeyAuth = Depends(get_api_key_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark messages as seen by the agent.

    Only marks messages that belong to this workspace and are user messages.
    """
    from sqlalchemy import update

    # Update messages that:
    # 1. Are in the list of message_ids
    # 2. Belong to this workspace
    # 3. Are user messages (user_id is not null)
    # 4. Haven't been seen yet (seen_at is null)
    result = await db.execute(
        update(Message)
        .where(Message.id.in_(data.message_ids))
        .where(Message.workspace_id == auth.workspace_id)
        .where(Message.user_id.isnot(None))
        .where(Message.seen_at.is_(None))
        .values(seen_at=datetime.utcnow())
    )
    await db.commit()

    return {
        "acknowledged": result.rowcount,
        "message_ids": data.message_ids,
    }


# Formatting instruction - always prepended to ensure clear, structured responses
FORMATTING_INSTRUCTION = (
    "[FORMATTING: Use markdown for clarity. Include code blocks with language hints "
    "(```python, ```bash, etc). Use bullet points for lists. Keep responses scannable "
    "with headers when appropriate. Structure complex information in tables when helpful. "
    "Be concise but complete.]\n\n"
)

# Default professional tone instruction - prepended when Dude Mode is OFF
DEFAULT_TONE_INSTRUCTION = (
    "[TONE: Respond in a professional, clear, and helpful manner. Be concise but thorough. "
    "Focus on delivering accurate information and completing tasks efficiently.]\n\n"
)

# Dude Mode instruction - prepended to user messages when enabled
DUDE_MODE_INSTRUCTION = (
    "[TONE: Respond in the style of The Dude from The Big Lebowski. "
    "Keep it casual and laid-back. Use phrases like 'yeah man', 'that's just like, "
    "your opinion, man', 'the Dude abides', and 'far out'. Stay chill but still "
    "do excellent work.]\n\n"
)

# Mai-Tai MCP tools reminder - reinforces proper tool usage during long sessions
MAI_TAI_TOOLS_INSTRUCTION = (
    "[MAI-TAI TOOLS: "
    "• update_status → quick progress updates (non-blocking) "
    "• chat_with_human → HOME BASE, REQUIRED when done or need answer (waits for response) "
    "NEVER go idle after a task - always call chat_with_human to report and get next instruction.]\n\n"
)

# Plan Mode instruction - when user wants discussion, not implementation
PLAN_MODE_INSTRUCTION = (
    "[PLANNING MODE: You are in planning/discussion mode. "
    "DO NOT write implementation code or create files. "
    "Instead: discuss approaches, ask clarifying questions, "
    "identify edge cases, propose architecture, and explore tradeoffs. "
    "When the user is ready to implement, they will disable plan mode. "
    "If the user asks you to implement something, remind them: "
    "\"You have plan mode enabled (💡 icon in chat header). "
    "Disable it when you're ready for me to code!\"]\n\n"
)


@router.get("/messages", response_model=MessageListResponse)
async def list_messages(
    limit: int = Query(50, le=100, ge=1),
    before: datetime | None = None,
    after: str | None = Query(None, description="Get messages after this message ID"),
    unseen: bool = Query(False, description="Only return unseen user messages"),
    auth: ApiKeyAuth = Depends(get_api_key_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get messages from the workspace.

    Use 'after' parameter to poll for new messages after a specific message ID.
    Use 'unseen=true' to get only user messages that haven't been acknowledged.
    """
    query = select(Message).where(Message.workspace_id == auth.workspace_id)

    # Filter for unseen user messages only
    if unseen:
        query = query.where(Message.seen_at.is_(None))
        query = query.where(Message.user_id.isnot(None))

    if after:
        # Get the 'after' message to find its created_at
        try:
            after_uuid = UUID(after)
            after_result = await db.execute(
                select(Message).where(Message.id == after_uuid)
            )
            after_msg = after_result.scalar_one_or_none()
            if after_msg:
                query = query.where(Message.created_at > after_msg.created_at)
        except ValueError:
            # Invalid UUID, ignore
            pass
    elif before:
        query = query.where(Message.created_at < before)

    query = query.order_by(Message.created_at.asc()).limit(limit + 1)

    result = await db.execute(query)
    messages = list(result.scalars().all())

    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]

    # Get sender names for user messages (for multi-human chat context)
    user_ids = [msg.user_id for msg in messages if msg.user_id]
    sender_names: dict[UUID, str] = {}
    if user_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        for user in users_result.scalars().all():
            sender_names[user.id] = user.name

    # Check workspace settings
    workspace_settings = auth.workspace.settings or {}
    dude_mode = workspace_settings.get("dude_mode", False)
    plan_mode = workspace_settings.get("plan_mode", False)
    project_context = workspace_settings.get("project_context", "")

    # Build modified messages with sender names and optional mode instructions
    modified_messages = []
    for msg in messages:
        content = msg.content
        sender_name = msg.agent_name  # Default to agent name

        # Add sender name for user messages
        if msg.user_id:
            sender_name = sender_names.get(msg.user_id, "Unknown User")
            content = f"[{sender_name}]: {content}"
            # Prepend formatting + tone + mai-tai tools instructions for user messages
            tone = DUDE_MODE_INSTRUCTION if dude_mode else DEFAULT_TONE_INSTRUCTION
            plan = PLAN_MODE_INSTRUCTION if plan_mode else ""
            project_ctx = f"\n\n[PROJECT CONTEXT: {project_context}]\n\n" if project_context else ""
            content = FORMATTING_INSTRUCTION + tone + plan + project_ctx + MAI_TAI_TOOLS_INSTRUCTION + content

        modified_messages.append({
            "id": msg.id,
            "workspace_id": msg.workspace_id,
            "user_id": msg.user_id,
            "agent_name": msg.agent_name,
            "sender_name": sender_name,
            "content": content,
            "message_metadata": msg.message_metadata,
            "created_at": msg.created_at,
            "seen_at": msg.seen_at,
        })

    return {"messages": modified_messages, "has_more": has_more, "total": len(modified_messages)}
