"""API key scopes — the capability tier of an agent credential.

The `api_keys.scopes` column has existed since the table did, and until now
nothing ever read it: every key was written `["read", "write"]` and every
endpoint accepted any valid key. That made "scope" a label rather than a
boundary, and it is the reason there is no way to hand out a credential that
can watch the fleet without also being able to speak as it.

Endpoints declare what they need with `deps.require_scope`, so the check lives
in exactly one place. Adding a scope means adding it here first — key creation
rejects names that aren't in this registry, because a typo'd scope on a key is
indistinguishable from a missing one until the day it matters.
"""

# Read workspace state: messages, schedules, workspace metadata.
READ = "read"

# Act in the workspace: post messages, acknowledge them, mutate schedules.
WRITE = "write"

# Observe and manage *other* workspaces' agents. No endpoint requires this
# yet — it is the tier the supervisor agent will hold, and it is defined here
# so that a key minted today can carry it and so nothing else accidentally
# claims the name.
FLEET = "fleet"

KNOWN_SCOPES: frozenset[str] = frozenset({READ, WRITE, FLEET})

# Everything an ordinary workspace agent needs, and the default for new keys.
DEFAULT_SCOPES: list[str] = [READ, WRITE]
