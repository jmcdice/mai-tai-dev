#!/bin/bash
# Regression cover for the coder-agent clone path (issues #39 and #41).
#
# #39: both `git config url...insteadOf` lines write the SAME key. Without
# --add the second replaces the first, so the https:// rewrite — the one a
# repo_url actually uses — silently disappears and every PRIVATE clone fails
# with "Repository not found". Public clones still work, which is why this
# went unnoticed.
#
# #41: a failed clone left no trace anywhere. Bootstrap now records the
# outcome so the backend can report the agent as degraded, and tells the
# agent itself so it stops describing an empty directory as the project.
#
# Runs offline: `git clone` is stubbed via PATH.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="${REPO_ROOT}/agents/common/bootstrap.sh"

PASS=0
FAIL=0

ok() { printf '  ok   %s\n' "$1"; PASS=$((PASS + 1)); }
no() { printf '  FAIL %s\n     %s\n' "$1" "${2:-}"; FAIL=$((FAIL + 1)); }

# --- Static check: --add on both rewrites -----------------------------------

echo "insteadOf configuration"

rewrite_lines="$(grep -c 'insteadOf' "${BOOTSTRAP}")"
add_lines="$(grep 'insteadOf' "${BOOTSTRAP}" | grep -c -- '--add')"

if [ "${rewrite_lines}" -eq "${add_lines}" ]; then
  ok "every insteadOf rewrite uses --add (${add_lines}/${rewrite_lines})"
else
  no "insteadOf rewrites must all use --add" \
     "${add_lines}/${rewrite_lines} do; without it they overwrite each other (#39)"
fi

# --- Behavioural check: git actually keeps both rewrites --------------------

echo "git config semantics"

CONFIG_HOME="$(mktemp -d)"
trap 'rm -rf "${CONFIG_HOME}"' EXIT
export HOME="${CONFIG_HOME}"
TOKEN="test-token"

git config --global --add url."https://x-access-token:${TOKEN}@github.com/".insteadOf "https://github.com/"
git config --global --add url."https://x-access-token:${TOKEN}@github.com/".insteadOf "git@github.com:"

kept="$(git config --global --get-all url."https://x-access-token:${TOKEN}@github.com/".insteadOf | wc -l)"
if [ "${kept}" -eq 2 ]; then
  ok "--add keeps both the https:// and git@ rewrites"
else
  no "expected 2 rewrites, kept ${kept}"
fi

if git config --global --get-all url."https://x-access-token:${TOKEN}@github.com/".insteadOf \
     | grep -qx "https://github.com/"; then
  ok "the https:// rewrite (the one repo_url uses) survives"
else
  no "https:// rewrite was lost — private clones will fail with 'Repository not found'"
fi

# Prove the bug the fix addresses: without --add, the second call clobbers.
git config --global --unset-all url."https://x-access-token:${TOKEN}@github.com/".insteadOf
git config --global url."https://x-access-token:${TOKEN}@github.com/".insteadOf "https://github.com/"
git config --global url."https://x-access-token:${TOKEN}@github.com/".insteadOf "git@github.com:"
clobbered="$(git config --global --get-all url."https://x-access-token:${TOKEN}@github.com/".insteadOf | wc -l)"
if [ "${clobbered}" -eq 1 ]; then
  ok "without --add only one rewrite survives (the bug this guards against)"
else
  no "expected the no---add form to clobber, kept ${clobbered}"
fi

# --- Behavioural check: a failed clone is recorded, not swallowed -----------

echo "failed clone reporting"

RUN_HOME="$(mktemp -d)"
STUB_BIN="${RUN_HOME}/bin"
mkdir -p "${STUB_BIN}"

# Stub git: succeed for everything except `clone`, which fails like a private
# repo with no usable credential.
# Real git echoes the rewritten URL — credential and all — into its error
# output, so the stub does too: the redaction below must be doing real work.
cat > "${STUB_BIN}/git" <<'STUB'
#!/bin/bash
if [ "${1:-}" = "clone" ]; then
  echo "remote: Repository not found." >&2
  echo "fatal: unable to access 'https://x-access-token:${GITHUB_TOKEN}@github.com/owner/private/': not found" >&2
  exit 128
fi
exec /usr/bin/git "$@"
STUB
chmod +x "${STUB_BIN}/git"

export HOME="${RUN_HOME}"
export PATH="${STUB_BIN}:${PATH}"
export MAI_TAI_API_URL="http://backend:8000"
export MAI_TAI_API_KEY="mt_test"
export MAI_TAI_WORKSPACE_ID="ws-test"
export MAI_TAI_MEMORY_DIR="${RUN_HOME}/memory"
export AGENT_WORKDIR="${RUN_HOME}/workspace"
export AGENT_TEMPLATE="coder"
export AGENT_NAME="TestCoder"
export REPO_URL="https://github.com/owner/private"
export GITHUB_TOKEN="super-secret-token"
export INSTRUCTIONS_FILE="CLAUDE.md"

if bash "${BOOTSTRAP}" > "${RUN_HOME}/bootstrap.log" 2>&1; then
  ok "bootstrap completes despite the clone failing"
else
  no "bootstrap exited non-zero" "$(tail -3 "${RUN_HOME}/bootstrap.log")"
fi

STATUS_FILE="${RUN_HOME}/.bootstrap-status"
if grep -q '"clone":"failed"' "${STATUS_FILE}" 2>/dev/null; then
  ok "clone failure is recorded in the bootstrap status marker"
else
  no "status marker does not record the failure" "$(cat "${STATUS_FILE}" 2>/dev/null)"
fi

if grep -q "Repository not found" "${STATUS_FILE}" 2>/dev/null; then
  ok "the git error is preserved for the API to surface"
else
  no "git's error was discarded"
fi

if grep -q "${GITHUB_TOKEN}" "${STATUS_FILE}" 2>/dev/null; then
  no "the GitHub token leaked into the status marker (the API hands this to the browser)"
else
  ok "the credential git echoed back is redacted from the status marker"
fi

if grep -qi "failed to clone" "${AGENT_WORKDIR}/CLAUDE.md" 2>/dev/null; then
  ok "the agent's own instructions say the repo is missing"
else
  no "the agent was not told its clone failed — it will describe an empty dir as the project"
fi

if grep -q "${GITHUB_TOKEN}" "${AGENT_WORKDIR}/CLAUDE.md" 2>/dev/null; then
  no "the GitHub token leaked into the agent's instructions file"
else
  ok "no credential in the agent's instructions file"
fi

# A successful clone must leave no warning behind.
export REPO_URL="https://github.com/owner/public"
cat > "${STUB_BIN}/git" <<'STUB'
#!/bin/bash
if [ "${1:-}" = "clone" ]; then
  mkdir -p "$3" && exit 0
fi
exec /usr/bin/git "$@"
STUB
chmod +x "${STUB_BIN}/git"
rm -rf "${AGENT_WORKDIR}"

if bash "${BOOTSTRAP}" > "${RUN_HOME}/bootstrap-ok.log" 2>&1 \
   && grep -q '"clone":"ok"' "${STATUS_FILE}" \
   && ! grep -qi "failed to clone" "${AGENT_WORKDIR}/CLAUDE.md"; then
  ok "a successful clone records ok and adds no warning"
else
  no "successful-clone path is wrong" "$(cat "${STATUS_FILE}")"
fi

rm -rf "${RUN_HOME}"

echo
echo "${PASS} passed, ${FAIL} failed"
[ "${FAIL}" -eq 0 ]
