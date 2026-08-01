#!/bin/bash
#
# mai-tai-config.sh - Export and import a full Mai-Tai deployment
#
# Produces a portable bundle you can carry to another machine to stand up an
# identical Mai-Tai: all workspaces, agents, users, and message history.
#
# SECRETS ARE NOT INCLUDED. Plaintext credentials living in users.settings
# (Anthropic keys, GitHub PATs, LLM keys) are stripped from the dump, and .env
# is never bundled. Copy .env over yourself at deploy time -- that keeps the
# bundle safe to store anywhere and makes moving credentials a deliberate act.
#
# Password hashes and mt_ API key hashes ARE included: they're hashes, not
# secrets, and keeping them means logins and existing agent configs keep
# working on the target once you bring your .env and ~/.config/mai-tai/config.
#
# USAGE:
#   ./mai-tai-config.sh export [output.tar.gz]   Write a bundle (default: mai-tai-export-<host>.tar.gz)
#   ./mai-tai-config.sh import <bundle.tar.gz>   Restore a bundle into this deployment
#   ./mai-tai-config.sh inspect <bundle.tar.gz>  Show what's inside without restoring
#   ./mai-tai-config.sh check-env                Report .env keys missing on this host
#
# REQUIREMENTS:
#   - docker, with the maitai-postgres container running
#   - Run from the repo root (or anywhere; paths resolve off this script)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PG_CONTAINER="${PG_CONTAINER:-maitai-postgres}"
PG_USER="${POSTGRES_USER:-maitai}"
PG_DB="${POSTGRES_DB:-maitai}"
# Throwaway database used to scrub secrets without touching the live one.
SCRATCH_DB="${PG_DB}_export_scrub"

BUNDLE_VERSION=1

# Keys in users.settings that hold plaintext credentials. Stripped on export.
SECRET_SETTINGS_KEYS=(anthropic_api_key github_token stash_llm_api_key)

# .env keys a target deployment needs to actually run.
REQUIRED_ENV_KEYS=(POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB SECRET_KEY NEXTAUTH_SECRET)
OPTIONAL_ENV_KEYS=(
  CLAUDE_CODE_USE_VERTEX ANTHROPIC_VERTEX_PROJECT_ID CLOUD_ML_REGION AGENT_MODEL
  AGENT_IMAGE GITHUB_CLIENT_ID GITHUB_CLIENT_SECRET GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET
)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[mai-tai-config]${NC} $*"; }
warn() { echo -e "${YELLOW}[mai-tai-config]${NC} $*" >&2; }
error() { echo -e "${RED}[mai-tai-config]${NC} $*" >&2; }
success() { echo -e "${GREEN}[mai-tai-config]${NC} $*"; }

require_pg() {
  if ! docker ps --format '{{.Names}}' | grep -qx "${PG_CONTAINER}"; then
    error "Postgres container '${PG_CONTAINER}' is not running."
    error "Start the stack first:  ./dev.sh local up"
    exit 1
  fi
}

# NOTE: no `docker exec -i` here. Query helpers must not attach stdin, or they
# swallow input the caller still needs -- e.g. the import confirmation prompt.
psql_q() {
  docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${PG_DB}" -tAc "$1"
}

# Cleanup state must be global: the EXIT trap fires outside function scope,
# where a `local` would be unset and trip `set -u`.
STAGE_DIR=""
SCRATCH_CREATED=0

cleanup() {
  [ -n "${STAGE_DIR}" ] && rm -rf "${STAGE_DIR}"
  # A scratch DB left behind holds unscrubbed live data under a name nobody
  # would think to look at. Always drop it, even on failure.
  if [ "${SCRATCH_CREATED}" = "1" ]; then
    docker exec "${PG_CONTAINER}" dropdb -U "${PG_USER}" --if-exists "${SCRATCH_DB}" \
      >/dev/null 2>&1 || true
  fi
  return 0
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

cmd_export() {
  require_pg

  local out="${1:-}"
  if [ -z "${out}" ]; then
    out="mai-tai-export-$(hostname -s).tar.gz"
  fi
  # Resolve to an absolute path before we cd into the staging dir.
  case "${out}" in
    /*) ;;
    *) out="$(pwd)/${out}" ;;
  esac

  local stage
  stage="$(mktemp -d)"
  STAGE_DIR="${stage}"

  # Scrub in a scratch copy of the database, not in the dump text and not by
  # appending an UPDATE to the restore. A trailing UPDATE would leave the
  # plaintext secrets sitting in the bundle's COPY blocks, and the COPY blocks
  # aren't safely regex-editable. Copy -> scrub -> dump is the only version
  # that guarantees the bytes on disk never held a credential.
  #
  # CREATE DATABASE ... TEMPLATE would be faster, but it requires zero other
  # sessions on the source — and the backend is always connected — so it never
  # actually wins here. Straight dump-and-reload instead.
  log "Building scrubbed copy of the database..."
  docker exec "${PG_CONTAINER}" dropdb -U "${PG_USER}" --if-exists "${SCRATCH_DB}" 2>/dev/null
  docker exec "${PG_CONTAINER}" createdb -U "${PG_USER}" "${SCRATCH_DB}"
  SCRATCH_CREATED=1
  docker exec "${PG_CONTAINER}" sh -c \
    "pg_dump -U '${PG_USER}' -d '${PG_DB}' | psql -q -o /dev/null -U '${PG_USER}' -d '${SCRATCH_DB}' -v ON_ERROR_STOP=1"

  log "Scrubbing secrets from users.settings..."
  local scrub="UPDATE users SET settings = settings"
  for key in "${SECRET_SETTINGS_KEYS[@]}"; do
    scrub+=" - '${key}'"
  done
  scrub+=" WHERE settings IS NOT NULL;"
  docker exec "${PG_CONTAINER}" psql -q -U "${PG_USER}" -d "${SCRATCH_DB}" \
    -v ON_ERROR_STOP=1 -c "${scrub}"

  # Assert the scrub actually landed before anything gets written to disk.
  local key_array residue
  key_array="$(printf "'%s'," "${SECRET_SETTINGS_KEYS[@]}" | sed 's/,$//')"
  residue="$(docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${SCRATCH_DB}" -tAc \
    "select count(*) from users where settings ?| array[${key_array}]")"
  if [ "${residue}" != "0" ]; then
    error "Scrub did not take — ${residue} user(s) still carry secret settings keys."
    exit 1
  fi

  log "Dumping scrubbed database..."
  docker exec "${PG_CONTAINER}" pg_dump -U "${PG_USER}" -d "${SCRATCH_DB}" \
    --clean --if-exists --no-owner --no-privileges \
    > "${stage}/database.sql"

  docker exec "${PG_CONTAINER}" dropdb -U "${PG_USER}" --if-exists "${SCRATCH_DB}"
  SCRATCH_CREATED=0

  # Belt and braces: scan the dump text for credential-shaped strings, so we
  # never ship a bundle that claims contains_secrets: false and lies. Requires
  # a plausible key *body*, not just a prefix — chat messages legitimately
  # discuss "sk-ant-..." and shouldn't trip this.
  if ! [ "${MAI_TAI_EXPORT_SKIP_SCAN:-}" = "1" ] && grep -qE \
      'sk-ant-[a-z0-9]+-[A-Za-z0-9_-]{30,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|BEGIN [A-Z ]*PRIVATE KEY' \
      "${stage}/database.sql"; then
    error "Refusing to write bundle: a live credential appears in the dump."
    error "Most likely someone pasted a key into a chat message. Redact it, or"
    error "re-run with MAI_TAI_EXPORT_SKIP_SCAN=1 to export anyway."
    error "Offending lines (truncated):"
    grep -nE 'sk-ant-[a-z0-9]+-[A-Za-z0-9_-]{30,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|BEGIN [A-Z ]*PRIVATE KEY' \
      "${stage}/database.sql" | cut -c1-100 | head -5 >&2
    exit 1
  fi

  log "Collecting manifest..."
  local counts
  counts="$(psql_q "
    select json_build_object(
      'users', (select count(*) from users),
      'workspaces', (select count(*) from workspaces),
      'agent_workspaces', (select count(*) from workspaces where workspace_type='agent'),
      'agents', (select count(*) from agents),
      'messages', (select count(*) from messages),
      'api_keys', (select count(*) from api_keys),
      'stash_links', (select count(*) from stash_links)
    )")"

  local schema_rev
  schema_rev="$(psql_q "select version_num from alembic_version limit 1" || echo "unknown")"

  python3 - "${stage}/manifest.json" "${counts}" "${schema_rev}" "${BUNDLE_VERSION}" <<'PY'
import json, sys, datetime, socket
out, counts, rev, ver = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
json.dump({
    "bundle_version": int(ver),
    "exported_at": datetime.datetime.now().astimezone().isoformat(),
    "source_host": socket.gethostname(),
    "alembic_revision": rev,
    "contains_secrets": False,
    "counts": json.loads(counts),
}, open(out, "w"), indent=2)
open(out, "a").write("\n")
PY

  # An .env template: every key the target needs, values blanked. Tells you
  # what to fill in without carrying any values across.
  log "Writing env.template..."
  {
    echo "# Generated by mai-tai-config.sh export from $(hostname -s)"
    echo "# Values are intentionally blank. Fill these in on the target, or copy"
    echo "# your real .env over separately."
    echo ""
    echo "# --- Required ---"
    for key in "${REQUIRED_ENV_KEYS[@]}"; do
      echo "${key}="
    done
    echo ""
    echo "# --- Optional (blank = feature off) ---"
    for key in "${OPTIONAL_ENV_KEYS[@]}"; do
      # Non-secret operational values are safe to carry, so keep them.
      case "${key}" in
        CLAUDE_CODE_USE_VERTEX|ANTHROPIC_VERTEX_PROJECT_ID|CLOUD_ML_REGION|AGENT_MODEL|AGENT_IMAGE)
          echo "${key}=$(get_env_value "${key}")"
          ;;
        *)
          echo "${key}="
          ;;
      esac
    done
  } > "${stage}/env.template"

  log "Packing bundle..."
  tar -czf "${out}" -C "${stage}" manifest.json database.sql env.template

  success "Wrote ${out} ($(du -h "${out}" | cut -f1))"
  echo ""
  python3 -c "
import json,sys
m=json.load(open('${stage}/manifest.json'))
for k,v in m['counts'].items():
    print(f'  {k:20} {v}')
"
  echo ""
  warn "No secrets in this bundle. On the target you still need to:"
  warn "  1. Copy your .env over (or fill in env.template)"
  warn "  2. Copy ~/.config/mai-tai/config if you want existing mt_ keys to work"
  warn "  3. Re-enter any Anthropic / GitHub / LLM keys in Settings > AI"
}

get_env_value() {
  local key="$1"
  if [ -f "${REPO_ROOT}/.env" ]; then
    grep -E "^${key}=" "${REPO_ROOT}/.env" 2>/dev/null | tail -1 | cut -d= -f2- || true
  fi
}

# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------

cmd_inspect() {
  local bundle="${1:?usage: mai-tai-config.sh inspect <bundle.tar.gz>}"
  [ -f "${bundle}" ] || { error "No such bundle: ${bundle}"; exit 1; }

  local stage
  stage="$(mktemp -d)"
  STAGE_DIR="${stage}"
  tar -xzf "${bundle}" -C "${stage}"

  log "Bundle: ${bundle}"
  echo ""
  cat "${stage}/manifest.json"
  echo ""
  log "Dump size: $(du -h "${stage}/database.sql" | cut -f1)"
}

# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

cmd_import() {
  local bundle="${1:?usage: mai-tai-config.sh import <bundle.tar.gz>}"
  [ -f "${bundle}" ] || { error "No such bundle: ${bundle}"; exit 1; }
  require_pg

  local stage
  stage="$(mktemp -d)"
  STAGE_DIR="${stage}"
  tar -xzf "${bundle}" -C "${stage}"

  [ -f "${stage}/database.sql" ] || { error "Bundle has no database.sql"; exit 1; }

  # Refuse bundles from a newer format than this script understands, rather
  # than silently restoring something whose layout has changed.
  local bundle_ver
  bundle_ver="$(python3 -c \
    "import json;print(json.load(open('${stage}/manifest.json')).get('bundle_version',0))" \
    2>/dev/null || echo 0)"
  if [ "${bundle_ver}" -gt "${BUNDLE_VERSION}" ]; then
    error "Bundle format v${bundle_ver} is newer than this script (v${BUNDLE_VERSION})."
    error "Update scripts/mai-tai-config.sh on this host first."
    exit 1
  fi

  local existing
  existing="$(psql_q "select count(*) from workspaces" 2>/dev/null || echo 0)"

  echo ""
  cat "${stage}/manifest.json"
  echo ""
  error "This REPLACES the database in '${PG_CONTAINER}' (${PG_DB})."
  error "It currently holds ${existing} workspace(s). They will be dropped."
  echo ""
  local confirm=""
  # Fail closed: no stdin (cron, CI) must abort, not fall through to a wipe.
  if ! read -r -p "Type 'replace' to continue: " confirm; then
    echo ""
    log "No input available. Aborted — nothing changed."
    exit 1
  fi
  if [ "${confirm}" != "replace" ]; then
    log "Aborted. Nothing changed."
    exit 0
  fi

  log "Restoring..."
  # ON_ERROR_STOP so a partial restore fails loudly instead of leaving a
  # half-populated database that looks fine until something queries it.
  if docker exec -i "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${PG_DB}" \
      -v ON_ERROR_STOP=1 --quiet -o /dev/null < "${stage}/database.sql"; then
    success "Database restored."
  else
    error "Restore failed. The database may be in a partial state."
    exit 1
  fi

  echo ""
  success "Import complete. Remaining manual steps:"
  echo "  1. Ensure .env is in place    ->  ./scripts/mai-tai-config.sh check-env"
  echo "  2. Restart the stack          ->  ./dev.sh local up"
  echo "  3. Re-enter credentials in Settings > AI (they were not exported)"
  echo ""
  log "Users needing credentials re-entered:"
  psql_q "select '  - ' || email from users order by email" || true
}

# ---------------------------------------------------------------------------
# check-env
# ---------------------------------------------------------------------------

cmd_check_env() {
  local envfile="${REPO_ROOT}/.env"
  if [ ! -f "${envfile}" ]; then
    error "No .env at ${envfile}"
    error "Copy one over, or start from .env.example"
    exit 1
  fi

  local missing=0
  log "Checking ${envfile}"
  echo ""
  echo "  Required:"
  for key in "${REQUIRED_ENV_KEYS[@]}"; do
    local val
    val="$(get_env_value "${key}")"
    if [ -z "${val}" ]; then
      echo -e "    ${RED}MISSING${NC}  ${key}"
      missing=$((missing + 1))
    else
      echo -e "    ${GREEN}ok${NC}       ${key}"
    fi
  done

  echo ""
  echo "  Optional:"
  for key in "${OPTIONAL_ENV_KEYS[@]}"; do
    local val
    val="$(get_env_value "${key}")"
    if [ -z "${val}" ]; then
      echo -e "    ${YELLOW}unset${NC}    ${key}"
    else
      echo -e "    ${GREEN}ok${NC}       ${key}"
    fi
  done

  echo ""
  if [ "${missing}" -gt 0 ]; then
    error "${missing} required key(s) missing — the stack will not come up cleanly."
    exit 1
  fi
  success "All required keys present."
}

# ---------------------------------------------------------------------------

usage() {
  sed -n '2,27p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

case "${1:-}" in
  export)    shift; cmd_export "$@" ;;
  import)    shift; cmd_import "$@" ;;
  inspect)   shift; cmd_inspect "$@" ;;
  check-env) shift; cmd_check_env "$@" ;;
  ""|-h|--help|help) usage ;;
  *) error "Unknown command: $1"; echo ""; usage; exit 1 ;;
esac
