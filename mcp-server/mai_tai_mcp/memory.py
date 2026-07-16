"""Persistent agent memory: curated MEMORY.md + daily journal.

Three memory kinds, following the OpenClaw/Hermes split:

- Curated semantic memory (MEMORY.md): small, size-capped, always loaded at
  session start. The cap is a feature — when a write would exceed it the
  operation fails and the agent must consolidate first.
- Episodic memory: the workspace message history, searched via the
  search_history tool (Postgres FTS on the backend) — unbounded, on demand.
- Journal (journal/YYYY-MM-DD.md): append-only daily notes; the driver loads
  today's and yesterday's entries at session start.

The memory directory is the per-workspace volume in containers
(MAI_TAI_MEMORY_DIR=/home/agent/memory) and a per-workspace dir under
~/.config/mai-tai/memory/<workspace_id> for host/BYO sessions.
"""

import os
from datetime import date, datetime
from pathlib import Path

# ~800 tokens. Small on purpose: forces consolidation, keeps every session's
# bootstrap cheap, and makes the agent choose what actually matters.
MEMORY_CHAR_LIMIT = 2200

JOURNAL_ENTRY_CHAR_LIMIT = 2000


def resolve_memory_dir(workspace_id: str | None = None) -> Path:
    """Resolve the memory directory for this agent."""
    env_dir = os.environ.get("MAI_TAI_MEMORY_DIR")
    if env_dir:
        return Path(env_dir)
    base = Path.home() / ".config" / "mai-tai" / "memory"
    return base / (workspace_id or "default")


def _memory_file(memory_dir: Path) -> Path:
    return memory_dir / "MEMORY.md"


def _journal_file(memory_dir: Path, day: date | None = None) -> Path:
    day = day or date.today()
    return memory_dir / "journal" / f"{day.isoformat()}.md"


def _usage(content: str) -> dict:
    return {
        "chars_used": len(content),
        "chars_limit": MEMORY_CHAR_LIMIT,
        "percent_used": round(100 * len(content) / MEMORY_CHAR_LIMIT),
    }


def read_memory(memory_dir: Path) -> str:
    """Read MEMORY.md, empty string if it doesn't exist."""
    f = _memory_file(memory_dir)
    return f.read_text(encoding="utf-8") if f.exists() else ""


def _write_memory(memory_dir: Path, content: str) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    _memory_file(memory_dir).write_text(content, encoding="utf-8")


def memory_add(memory_dir: Path, content: str) -> dict:
    """Append an entry to MEMORY.md, enforcing the size cap."""
    content = content.strip()
    if not content:
        return {"status": "error", "error": "Empty content."}

    existing = read_memory(memory_dir)
    combined = (existing.rstrip() + "\n" + content + "\n") if existing else content + "\n"

    if len(combined) > MEMORY_CHAR_LIMIT:
        return {
            "status": "error",
            "error": (
                f"MEMORY.md would exceed its {MEMORY_CHAR_LIMIT}-char limit "
                f"({len(combined)} chars). Consolidate first: use action='replace' "
                "or action='remove' to compress or prune existing entries, then retry. "
                "Keep only durable facts — session details belong in the journal."
            ),
            **_usage(existing),
        }

    _write_memory(memory_dir, combined)
    return {"status": "ok", **_usage(combined)}


def memory_replace(memory_dir: Path, old_content: str, new_content: str) -> dict:
    """Replace an entry in MEMORY.md by substring match."""
    existing = read_memory(memory_dir)
    if old_content not in existing:
        return {"status": "error", "error": "old_content not found in MEMORY.md."}

    updated = existing.replace(old_content, new_content.strip(), 1)
    if len(updated) > MEMORY_CHAR_LIMIT:
        return {
            "status": "error",
            "error": f"Replacement would exceed the {MEMORY_CHAR_LIMIT}-char limit. Write a shorter entry.",
            **_usage(existing),
        }

    _write_memory(memory_dir, updated)
    return {"status": "ok", **_usage(updated)}


def memory_remove(memory_dir: Path, old_content: str) -> dict:
    """Remove an entry from MEMORY.md by substring match."""
    existing = read_memory(memory_dir)
    if old_content not in existing:
        return {"status": "error", "error": "old_content not found in MEMORY.md."}

    updated = existing.replace(old_content, "", 1)
    # Collapse the blank lines a removal leaves behind
    while "\n\n\n" in updated:
        updated = updated.replace("\n\n\n", "\n\n")
    _write_memory(memory_dir, updated.strip() + "\n" if updated.strip() else "")
    return {"status": "ok", **_usage(updated)}


def journal_append(memory_dir: Path, entry: str) -> dict:
    """Append a timestamped entry to today's journal."""
    entry = entry.strip()
    if not entry:
        return {"status": "error", "error": "Empty entry."}
    if len(entry) > JOURNAL_ENTRY_CHAR_LIMIT:
        return {
            "status": "error",
            "error": f"Journal entries are capped at {JOURNAL_ENTRY_CHAR_LIMIT} chars. Summarize.",
        }

    f = _journal_file(memory_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H:%M")
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(f"- [{stamp}] {entry}\n")
    return {"status": "ok", "file": str(f)}


def build_session_context(memory_dir: Path, lookback_days: int = 2) -> str:
    """Assemble the session-start memory block: MEMORY.md + recent journal.

    The driver writes this to memory/context.md, which the agent's
    instructions file imports — so every fresh session starts with memory.
    """
    parts: list[str] = []

    memory = read_memory(memory_dir)
    if memory.strip():
        parts.append("## Curated memory (MEMORY.md)\n" + memory.strip())

    journal_dir = memory_dir / "journal"
    if journal_dir.is_dir():
        days = sorted(journal_dir.glob("*.md"), reverse=True)[:lookback_days]
        for f in reversed(days):
            content = f.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"## Journal {f.stem}\n" + content)

    lessons = memory_dir / "tasks" / "lessons.md"
    if lessons.exists():
        content = lessons.read_text(encoding="utf-8").strip()
        if content:
            parts.append("## Lessons learned\n" + content)

    if not parts:
        return "(no persistent memory yet)"
    return "\n\n".join(parts)
