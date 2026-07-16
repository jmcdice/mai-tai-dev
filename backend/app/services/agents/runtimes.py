"""Agent runtime registry.

Each runtime describes an agent CLI packaged as a Docker image, the models it
supports, and which user credential it needs. Adding a runtime means adding a
RuntimeSpec here plus an agents/<id>/ image in the repo — the spawner and API
are runtime-agnostic.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuntimeSpec:
    """A supported agent runtime."""

    id: str
    label: str
    description: str
    default_image: str
    # users.settings key holding the credential this runtime needs
    credential_setting: str
    credential_label: str
    default_model: str
    # Curated model choices for the UI: [{"id": ..., "label": ...}]
    models: list[dict] = field(default_factory=list)
    enabled: bool = True

    @property
    def image(self) -> str:
        """Docker image, overridable per runtime via environment.

        The legacy AGENT_IMAGE var keeps working for claude-code; other
        runtimes use AGENT_IMAGE_<ID> (e.g. AGENT_IMAGE_CODEX).
        """
        if self.id == "claude-code":
            return os.environ.get("AGENT_IMAGE", self.default_image)
        env_key = f"AGENT_IMAGE_{self.id.upper().replace('-', '_')}"
        return os.environ.get(env_key, self.default_image)


RUNTIMES: dict[str, RuntimeSpec] = {
    "claude-code": RuntimeSpec(
        id="claude-code",
        label="Claude Code",
        description="Anthropic's coding agent. Works with an Anthropic API key or a Pro/Max OAuth token.",
        default_image="mai-tai-agent:latest",
        credential_setting="anthropic_api_key",
        credential_label="Anthropic API key",
        default_model="sonnet",
        models=[
            {"id": "haiku", "label": "Haiku (fast, cheap)"},
            {"id": "sonnet", "label": "Sonnet (balanced)"},
            {"id": "opus", "label": "Opus (most capable)"},
        ],
    ),
    "codex": RuntimeSpec(
        id="codex",
        label="OpenAI Codex",
        description="OpenAI's coding agent. Requires an OpenAI API key.",
        default_image="mai-tai-agent-codex:latest",
        credential_setting="openai_api_key",
        credential_label="OpenAI API key",
        default_model="gpt-5-codex",
        models=[
            {"id": "gpt-5-codex", "label": "GPT-5 Codex"},
            {"id": "gpt-5-mini", "label": "GPT-5 Mini (fast, affordable)"},
        ],
        enabled=False,  # flips on when the codex image lands
    ),
}


def get_runtime(runtime_id: str) -> RuntimeSpec | None:
    """Look up a runtime by id."""
    return RUNTIMES.get(runtime_id)
