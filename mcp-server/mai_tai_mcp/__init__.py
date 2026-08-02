"""Mai-Tai MCP Server - Connect your coding agent to mai-tai."""

from importlib.metadata import PackageNotFoundError, version as _installed_version

# Read from the installed distribution rather than restating it here. This was
# a hand-maintained literal and it drifted: 0.6.0 shipped with the string still
# saying 0.5.0. That number is printed in the config-error banner — the one
# place a confused user reads the version off the screen and tells you what
# they're running — so a stale value there sends you debugging the wrong build.
try:
    __version__ = _installed_version("mai-tai-mcp")
except PackageNotFoundError:
    # Imported straight from a source checkout with nothing installed.
    __version__ = "0.0.0+source"

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
