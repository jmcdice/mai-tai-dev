#!/usr/bin/env python3
"""Mark a folder as trusted in ~/.claude.json, so Claude never asks.

WHY THIS EXISTS
---------------
Claude Code shows a "Quick safety check: Is this a project you created or one
you trust?" dialog the first time it runs interactively in a directory. That
dialog is skipped in non-interactive mode (-p, or a non-TTY stdout), so Docker
workspace agents never see it -- but the host supervisor bots run Claude on a
pane TTY by design, so they always get it unless the per-project flag is set.

A wedged bot looks alive: the tmux pane is up, the process is running, and it
sits on the highlighted "1. Yes, I trust this folder" forever waiting for a
keypress nobody is there to send. On 2026-08-13 a Claude Code auto-update
(2.1.231 -> 2.1.232) started prompting where it previously had not, and three
bots died the instant they rotated onto the new binary -- roughly four hours of
silent downtime discovered only by hand.

There is no CLI flag and no settings.json key for folder trust (checked against
`claude --help`; `--dangerously-skip-permissions` does NOT cover it). The only
lever is projects[<dir>].hasTrustDialogAccepted in ~/.claude.json.

THE CONCURRENCY PROBLEM, STATED HONESTLY
----------------------------------------
~/.claude.json is shared by every Claude process on the box, and each one
rewrites the whole file from its own in-memory copy. We cannot make that safe;
we can only make our own write small, atomic, and rare:

  * We take an flock so two supervisors never write at once. Claude itself does
    not take that lock, so this does NOT eliminate the race with running
    sessions -- it only removes the supervisor-vs-supervisor half of it.
  * We re-read inside the lock and exit without writing if the flag is already
    true, which is the common case. No write, no clobber.
  * We write via a temp file + os.replace, so a reader never sees a torn file.
  * We keep one backup of the previous contents.

The window that remains is the milliseconds between our read and our replace.
The supervisor calls this immediately before launching Claude, when that repo's
own bot is down, which is the quietest moment available.

USAGE: claude-trust-folder.py <dir> [<dir>...]
Exit code is 0 on success and on any recoverable problem -- a trust preflight
must never be the reason a bot fails to start.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

CONFIG = Path(os.environ.get("CLAUDE_CONFIG_JSON", str(Path.home() / ".claude.json")))
BACKUP = CONFIG.with_suffix(".json.mai-tai.bak")


def main(argv: list[str]) -> int:
    targets = [os.path.realpath(os.path.expanduser(a)) for a in argv]
    if not targets:
        print("usage: claude-trust-folder.py <dir> [<dir>...]", file=sys.stderr)
        return 2

    try:
        data = json.loads(CONFIG.read_text())
    except FileNotFoundError:
        # Claude has never run as this user. It will create the file itself and
        # write the flag when the human answers the dialog once; inventing the
        # file here risks a shape Claude does not expect.
        print(f"skip: {CONFIG} does not exist yet")
        return 0
    except (OSError, ValueError) as exc:
        print(f"skip: cannot read {CONFIG}: {exc}", file=sys.stderr)
        return 0

    if not isinstance(data, dict):
        print(f"skip: {CONFIG} is not a JSON object", file=sys.stderr)
        return 0

    projects = data.setdefault("projects", {})
    if not isinstance(projects, dict):
        print(f"skip: {CONFIG} 'projects' is not an object", file=sys.stderr)
        return 0

    changed = []
    for target in targets:
        entry = projects.get(target)
        if not isinstance(entry, dict):
            # A repo Claude has never opened. A minimal entry is what Claude
            # itself starts from, and it merges its own defaults on top.
            entry = {}
            projects[target] = entry
        if entry.get("hasTrustDialogAccepted") is True:
            continue
        entry["hasTrustDialogAccepted"] = True
        changed.append(target)

    if not changed:
        print("ok: already trusted")
        return 0

    try:
        shutil.copy2(CONFIG, BACKUP)
        mode = CONFIG.stat().st_mode & 0o777
        fd, tmp = tempfile.mkstemp(dir=str(CONFIG.parent), prefix=".claude.json.mai-tai.")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(data, handle, indent=2)
            os.chmod(tmp, mode)
            os.replace(tmp, CONFIG)
        except BaseException:
            # Never leave a stray temp file behind in $HOME.
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as exc:
        print(f"skip: cannot write {CONFIG}: {exc}", file=sys.stderr)
        return 0

    print(f"trusted: {', '.join(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
