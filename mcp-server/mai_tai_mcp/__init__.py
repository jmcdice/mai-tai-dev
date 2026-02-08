"""Mai-Tai MCP Server - Connect your coding agent to mai-tai."""

__version__ = "0.4.4"

from .backend import MaiTaiBackend, MaiTaiBackendError, create_backend
from .backoff import BackoffState, wait_with_backoff, should_retry
from .communication import (
    DecisionCategory,
    DecisionContext,
    MessagePriority,
    ask_for_decision,
    chat_with_human,
    format_decision_request,
    get_recommended_timeout,
    should_ask_human,
)
from .config import ConfigurationError, MaiTaiConfig, get_config
from .errors import (
    FatalRuntimeError,
    MaiTaiError,
    RecoverableError,
    classify_http_error,
)
from .observability import (
    EventType,
    Metrics,
    get_metrics,
    get_status_summary,
    log_connection_attempt,
    log_connection_failed,
    log_connection_lost,
    log_connection_success,
    log_fatal_error,
    log_mai_tai_enter,
    log_mai_tai_exit,
    log_mai_tai_task_complete,
    log_message_received,
    log_message_sent,
    log_recoverable_error,
    log_reconnect_attempt,
    reset_metrics,
)
from .mode_handlers import (
    handle_enter_mai_tai_mode,
    handle_exit_mai_tai_mode,
    handle_plan_received,
    handle_task_complete,
    is_exit_request,
    send_progress_update,
    send_blocked_message,
)
from .server import main, mcp
from .state import (
    ActivityStatus,
    EntryScenario,
    MaiTaiState,
    PlanStep,
    WorkPlan,
)
from .ws_client import ConnectionState, WebSocketClient, WorkspaceSubscription, create_ws_client

__all__ = [
    # Backend
    "MaiTaiBackend",
    "MaiTaiBackendError",
    "create_backend",
    # Config
    "ConfigurationError",
    "MaiTaiConfig",
    "get_config",
    # Errors (v2)
    "FatalRuntimeError",
    "MaiTaiError",
    "RecoverableError",
    "classify_http_error",
    # Backoff (v2)
    "BackoffState",
    "wait_with_backoff",
    "should_retry",
    # Communication (v2)
    "DecisionCategory",
    "DecisionContext",
    "MessagePriority",
    "ask_for_decision",
    "chat_with_human",
    "format_decision_request",
    "get_recommended_timeout",
    "should_ask_human",
    # WebSocket (v3)
    "ConnectionState",
    "WebSocketClient",
    "WorkspaceSubscription",
    "create_ws_client",
    # Observability (v2)
    "EventType",
    "Metrics",
    "get_metrics",
    "get_status_summary",
    "log_connection_attempt",
    "log_connection_failed",
    "log_connection_lost",
    "log_connection_success",
    "log_fatal_error",
    "log_mai_tai_enter",
    "log_mai_tai_exit",
    "log_mai_tai_task_complete",
    "log_message_received",
    "log_message_sent",
    "log_recoverable_error",
    "log_reconnect_attempt",
    "reset_metrics",
    # State (v2)
    "ActivityStatus",
    "EntryScenario",
    "MaiTaiState",
    "PlanStep",
    "WorkPlan",
    # Mode handlers (v2)
    "handle_enter_mai_tai_mode",
    "handle_exit_mai_tai_mode",
    "handle_plan_received",
    "handle_task_complete",
    "is_exit_request",
    "send_progress_update",
    "send_blocked_message",
    # Server
    "main",
    "mcp",
]

