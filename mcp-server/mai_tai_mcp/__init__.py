"""Mai-Tai MCP Server - Connect your coding agent to mai-tai."""

__version__ = "0.5.0"

from .backend import MaiTaiBackend, MaiTaiBackendError, create_backend
from .config import ConfigurationError, MaiTaiConfig, get_config
from .errors import (
    FatalRuntimeError,
    MaiTaiError,
    RecoverableError,
    classify_http_error,
)
from .server import main, mcp

__all__ = [
    # Backend
    "MaiTaiBackend",
    "MaiTaiBackendError",
    "create_backend",
    # Config
    "ConfigurationError",
    "MaiTaiConfig",
    "get_config",
    # Errors
    "FatalRuntimeError",
    "MaiTaiError",
    "RecoverableError",
    "classify_http_error",
    # Server
    "main",
    "mcp",
]
