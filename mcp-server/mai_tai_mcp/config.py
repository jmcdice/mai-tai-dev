"""Configuration management for mai-tai MCP server (v4 - user-level API keys).

v4 Config Model (hierarchical):
1. Global config: ~/.config/mai-tai/config (API URL and API key)
2. Project config: .env.mai-tai in CWD (workspace ID)
3. Environment variables (override everything)

This allows users to:
- Set API URL and API key once globally
- Set workspace ID per-project
- Override anything via environment variables
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from mai_tai_mcp import __version__


class ConfigurationError(Exception):
    """Raised when Mai-Tai MCP configuration is invalid or incomplete."""

    pass


class MaiTaiConfig(BaseModel):
    """Mai-tai connection configuration (v4 - user-level API keys).

    All three fields are required. Values are loaded hierarchically:
    1. ~/.config/mai-tai/config (global)
    2. .env.mai-tai (per-project)
    3. Environment variables (override)
    """

    api_url: str = Field(
        ..., description="Mai-tai backend URL (e.g., https://api.mai-tai.dev)"
    )
    api_key: str = Field(
        ..., description="Mai-tai API key (user-level, starts with mt_)"
    )
    workspace_id: str = Field(
        ..., description="Mai-tai workspace ID (from workspace settings)"
    )


def _load_config_file(path: Path) -> Dict[str, str]:
    """Load key=value pairs from a config file.

    Supports simple KEY=VALUE format (one per line).
    Lines starting with # are comments.
    Empty lines are ignored.
    """
    config: Dict[str, str] = {}
    if not path.exists():
        return config

    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    # Remove surrounding quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    if key:
                        config[key] = value
    except (IOError, OSError):
        pass  # Ignore file read errors

    return config


def _find_project_env_file() -> Optional[Path]:
    """Find .env.mai-tai by checking CWD and PWD env var.

    Claude Code spawns global MCP servers with a different CWD than the
    user's project directory. The PWD environment variable, inherited from
    the shell, reflects the actual working directory the user is in.
    """
    candidates = [Path.cwd()]
    pwd = os.environ.get("PWD", "").strip()
    if pwd:
        pwd_path = Path(pwd)
        if pwd_path != Path.cwd():
            candidates.append(pwd_path)

    for directory in candidates:
        candidate = directory / ".env.mai-tai"
        if candidate.exists():
            return candidate

    return None


def _load_hierarchical_config() -> Dict[str, str]:
    """Load configuration from hierarchical sources.

    Priority (highest to lowest):
    1. Environment variables
    2. .env.mai-tai in current directory (per-project)
    3. ~/.config/mai-tai/config (global)

    Returns merged config dict.
    """
    config: Dict[str, str] = {}

    # 1. Load global config (lowest priority)
    global_config_path = Path.home() / ".config" / "mai-tai" / "config"
    config.update(_load_config_file(global_config_path))

    # 2. Load per-project config (overrides global)
    project_config_path = _find_project_env_file()
    if project_config_path:
        config.update(_load_config_file(project_config_path))

    # 3. Environment variables override everything
    for key in ["MAI_TAI_API_URL", "MAI_TAI_API_KEY", "MAI_TAI_WORKSPACE_ID"]:
        env_value = os.getenv(key, "").strip()
        if env_value:
            config[key] = env_value

    return config


def _build_config_error_message(missing_vars: List[str]) -> str:
    """Build a clear, actionable error message for missing config."""
    vars_list = ", ".join(missing_vars)
    return (
        f"mai-tai-mcp v{__version__}\n"
        f"\n"
        f"Configuration error: missing required value(s): {vars_list}\n"
        f"\n"
        f"Configuration is loaded from (in order of priority):\n"
        f"  1. Environment variables (highest priority)\n"
        f"  2. .env.mai-tai in current directory (per-project)\n"
        f"  3. ~/.config/mai-tai/config (global)\n"
        f"\n"
        f"Recommended setup:\n"
        f"  1. Create ~/.config/mai-tai/config with:\n"
        f"     MAI_TAI_API_URL=https://api.mai-tai.dev\n"
        f"     MAI_TAI_API_KEY=mt_your_api_key_here\n"
        f"\n"
        f"  2. Create .env.mai-tai in each project with:\n"
        f"     MAI_TAI_WORKSPACE_ID=your-workspace-uuid\n"
        f"\n"
        f"Get these values from your mai-tai account settings."
    )


def is_project_configured() -> bool:
    """Check if the current project is configured for mai-tai.

    A project is considered "configured" if either:
    1. A .env.mai-tai file exists in the current directory (or PWD), OR
    2. The MAI_TAI_WORKSPACE_ID environment variable is set

    This is used to determine whether to fail silently (not configured)
    or show helpful error messages (configured but incomplete).

    Returns:
        True if the project has mai-tai configuration, False otherwise.
    """
    # Check for .env.mai-tai file (checks both CWD and PWD env var)
    if _find_project_env_file() is not None:
        return True

    # Check for MAI_TAI_WORKSPACE_ID environment variable
    if os.getenv("MAI_TAI_WORKSPACE_ID", "").strip():
        return True

    return False


def get_config() -> MaiTaiConfig:
    """Get mai-tai configuration from hierarchical sources.

    Loads config from:
    1. ~/.config/mai-tai/config (global: API URL, API key)
    2. .env.mai-tai (per-project: workspace ID)
    3. Environment variables (override)

    Raises:
        ConfigurationError: If required values are missing.
    """
    config = _load_hierarchical_config()

    missing: List[str] = []
    api_url = config.get("MAI_TAI_API_URL", "").strip()
    api_key = config.get("MAI_TAI_API_KEY", "").strip()
    workspace_id = config.get("MAI_TAI_WORKSPACE_ID", "").strip()

    if not api_url:
        missing.append("MAI_TAI_API_URL")
    if not api_key:
        missing.append("MAI_TAI_API_KEY")
    if not workspace_id:
        missing.append("MAI_TAI_WORKSPACE_ID")

    if missing:
        raise ConfigurationError(_build_config_error_message(missing))

    return MaiTaiConfig(api_url=api_url, api_key=api_key, workspace_id=workspace_id)

