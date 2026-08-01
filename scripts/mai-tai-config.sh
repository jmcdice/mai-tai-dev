#!/bin/bash
#
# mai-tai-config.sh - Export and import a full Mai-Tai deployment
#
# Produces a portable bundle you can carry to another machine to stand up an
# identical Mai-Tai: all users, workspaces, agents, and message history.
#
# THE BUNDLE IS A SECRET. By default the dump is byte-for-byte complete, which
# means the plaintext credentials stored in users.settings (Anthropic key,
# GitHub token, LLM keys) come with it. That's deliberate -- it makes the
# target a working copy with no re-entry hoops. The tradeoff is that the .tar.gz
# is now credential material: it's written mode 0600, and you should delete it
# once the move is done. Pass --scrub for a credential-free bundle instead.
#
# USAGE:
#   ./mai-tai-config.sh export [opts] [out.tar.gz]  Write a bundle
#       --scrub      Strip plaintext credentials from users.settings
#       --with-env   Also bundle .env (off by default)
#   ./mai-tai-config.sh import <bundle.tar.gz>      Restore into this deployment
#   ./mai-tai-config.sh inspect <bundle.tar.gz>     Show contents without restoring
#   ./mai-tai-config.sh check-env                   Report .env keys missing here
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

BUNDLE_VERSION=2

# Keys in users.settings that hold credentials (Fernet-encrypted at rest since
# backend/app/core/crypto.py landed). Stripped by --scrub. Keep in sync with
# SENSITIVE_USER_SETTINGS there.
SECRET_SETTINGS_KEYS=(anthropic_api_key openai_api_key github_token stash_llm_api_key)

# .env keys a target deployment needs to actually run.
#
# ENCRYPTION_KEY is optional in the sense that crypto.py derives a key from
# SECRET_KEY when it's unset — but if the source host set it, the target must
# use the same value or every stored credential in the dump decrypts to
# nothing. Same for SECRET_KEY under the fallback. check-env flags both.
REQUIRED_ENV_KEYS=(POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB SECRET_KEY NEXTAUTH_SECRET)
OPTIONAL_ENV_KEYS=(
  ENCRYPTION_KEY
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

  local out="" scrub_secrets=0 with_env=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --scrub)    scrub_secrets=1 ;;
      --with-env) with_env=1 ;;
      -*) error "Unknown option: $1"; exit 1 ;;
      *)  out="$1" ;;
    esac
    shift
  done

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
  chmod 700 "${stage}"

  if [ "${scrub_secrets}" = "1" ]; then
    # Scrub in a scratch copy of the database, not in the dump text and not by
    # appending an UPDATE to the restore. A trailing UPDATE would leave the
    # plaintext secrets sitting in the bundle's COPY blocks, and the COPY
    # blocks aren't safely regex-editable. Copy -> scrub -> dump is the only
    # version that guarantees the bytes on disk never held a credential.
    #
    # CREATE DATABASE ... TEMPLATE would be faster, but it needs zero other
    # sessions on the source -- and the backend is always connected -- so it
    # never actually wins here. Straight dump-and-reload instead.
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

    # Assert the scrub landed before anything reaches disk.
    local key_array residue
    key_array="$(printf "'%s'," "${SECRET_SETTINGS_KEYS[@]}" | sed 's/,$//')"
    residue="$(docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${SCRATCH_DB}" -tAc \
      "select count(*) from users where settings ?| array[${key_array}]")"
    if [ "${residue}" != "0" ]; then
      error "Scrub did not take -- ${residue} user(s) still carry secret settings keys."
      exit 1
    fi

    log "Dumping scrubbed database..."
    docker exec "${PG_CONTAINER}" pg_dump -U "${PG_USER}" -d "${SCRATCH_DB}" \
      --clean --if-exists --no-owner --no-privileges \
      > "${stage}/database.sql"

    docker exec "${PG_CONTAINER}" dropdb -U "${PG_USER}" --if-exists "${SCRATCH_DB}"
    SCRATCH_CREATED=0
  else
    log "Dumping database from ${PG_CONTAINER}..."
    docker exec "${PG_CONTAINER}" pg_dump -U "${PG_USER}" -d "${PG_DB}" \
      --clean --if-exists --no-owner --no-privileges \
      > "${stage}/database.sql"
  fi

  # Optionally carry .env. Off by default so a bundle can't leak infra
  # credentials nobody realised were in scope.
  local env_included=false
  if [ "${with_env}" = "1" ]; then
    if [ -f "${REPO_ROOT}/.env" ]; then
      cp "${REPO_ROOT}/.env" "${stage}/env"
      env_included=true
      log "Including .env in the bundle."
    else
      warn "--with-env given but no .env at ${REPO_ROOT}/.env — skipping."
    fi
  fi

  log "Collecting manifest..."
  local counts
  counts="$(psql_q "
    select json_build_object(
      'users', (select count(*) from users),
      'workspaces', (select count(*) from workspaces),
      'agent_workspaces', (select count(*) from workspaces where workspace_type='agent'),
      'messages', (select count(*) from messages),
      'api_keys', (select count(*) from api_keys),
      'stash_links', (select count(*) from stash_links)
    )")"

  local schema_rev
  schema_rev="$(psql_q "select version_num from alembic_version limit 1" || echo "unknown")"

  local has_secrets=true
  [ "${scrub_secrets}" = "1" ] && has_secrets=false

  python3 - "${stage}/manifest.json" "${counts}" "${schema_rev}" "${BUNDLE_VERSION}" \
      "${has_secrets}" "${env_included}" "$(crypto_fingerprint)" <<'PY'
import json, sys, datetime, socket
out, counts, rev, ver, secrets, envinc, fp = sys.argv[1:8]
json.dump({
    "bundle_version": int(ver),
    "exported_at": datetime.datetime.now().astimezone().isoformat(),
    "source_host": socket.gethostname(),
    "alembic_revision": rev,
    "contains_secrets": secrets == "true",
    "includes_env": envinc == "true",
    "crypto_fingerprint": fp,
    "counts": json.loads(counts),
}, open(out, "w"), indent=2)
open(out, "a").write("\n")
PY

  # A blank .env template so a fresh target knows what to fill in. Operational
  # (non-credential) values are carried through; everything else stays empty.
  log "Writing env.template..."
  {
    echo "# Generated by mai-tai-config.sh export from $(hostname -s)"
    echo "# Credential values are intentionally blank -- fill them in on the target."
    echo ""
    echo "# --- Required ---"
    for key in "${REQUIRED_ENV_KEYS[@]}"; do
      echo "${key}="
    done
    echo ""
    echo "# --- Optional (blank = feature off) ---"
    for key in "${OPTIONAL_ENV_KEYS[@]}"; do
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
  # Create it 0600 *before* writing, so the contents are never briefly
  # world-readable on a shared box.
  rm -f "${out}"
  (umask 077 && touch "${out}")
  local members="manifest.json database.sql env.template"
  [ "${env_included}" = "true" ] && members="${members} env"
  # shellcheck disable=SC2086
  tar -czf "${out}" -C "${stage}" ${members}
  chmod 600 "${out}"

  success "Wrote ${out} ($(du -h "${out}" | cut -f1), mode 0600)"
  echo ""
  python3 -c "
import json
m=json.load(open('${stage}/manifest.json'))
for k,v in m['counts'].items():
    print(f'  {k:20} {v}')
"
  echo ""
  if [ "${scrub_secrets}" = "1" ]; then
    log "Scrubbed bundle — no credentials inside. On the target you'll need to:"
    log "  1. Put .env in place    (./scripts/mai-tai-config.sh check-env)"
    log "  2. Copy ~/.config/mai-tai/config so existing mt_ keys authenticate"
    log "  3. Re-enter Anthropic / GitHub / LLM keys in Settings > AI"
  else
    local env_note=""
    [ "${env_included}" = "true" ] && env_note=" and your .env"
    error "TREAT THIS FILE AS A SECRET."
    error "It carries the credentials from users.settings (Anthropic/OpenAI keys,"
    error "GitHub token, LLM keys)${env_note}, plus full message history."
    error "Those settings are Fernet-encrypted at rest, but the key derives from"
    error "SECRET_KEY unless ENCRYPTION_KEY is set -- a bundle plus a leaked .env"
    error "is plaintext. Don't commit it, don't put it in cloud storage, and"
    error "delete it once the move is done."
    echo ""
    log "Use --scrub for a credential-free bundle that's safe to store."
  fi
}

get_env_value() {
  local key="$1"
  if [ -f "${REPO_ROOT}/.env" ]; then
    grep -E "^${key}=" "${REPO_ROOT}/.env" 2>/dev/null | tail -1 | cut -d= -f2- || true
  fi
}

# Identifies the key that Fernet-encrypts users.settings, without revealing it.
# crypto.py uses ENCRYPTION_KEY when set and otherwise derives one from
# SECRET_KEY, so only the effective key is fingerprinted. Import compares this
# against the target's own -- a mismatch means every credential in the dump
# decrypts to nothing, which is otherwise silent until an agent fails to start.
crypto_fingerprint() {
  local enc sec
  enc="$(get_env_value ENCRYPTION_KEY)"
  sec="$(get_env_value SECRET_KEY)"
  if [ -n "${enc}" ]; then
    printf 'enc:%s' "${enc}" | sha256sum | cut -c1-16
  elif [ -n "${sec}" ]; then
    printf 'sec:%s' "${sec}" | sha256sum | cut -c1-16
  else
    echo "unknown"
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

  # users.settings credentials are Fernet-encrypted with a key derived from the
  # source's .env. If the target's key differs they restore as undecryptable
  # noise -- and nothing surfaces that until an agent refuses to start. Say so
  # while the operator can still fix the .env.
  local src_fp
  src_fp="$(python3 -c \
    "import json;print(json.load(open('${stage}/manifest.json')).get('crypto_fingerprint',''))" \
    2>/dev/null || echo "")"
  if [ -n "${src_fp}" ] && [ "${src_fp}" != "unknown" ]; then
    local dst_fp
    dst_fp="$(crypto_fingerprint)"
    if [ "${dst_fp}" != "${src_fp}" ]; then
      warn "Encryption key mismatch (source ${src_fp}, here ${dst_fp})."
      warn "Stored credentials will not decrypt on this host. Copy ENCRYPTION_KEY"
      warn "and SECRET_KEY from the source .env before importing, or plan to"
      warn "re-enter every key in Settings > AI afterwards."
      echo ""
    fi
  fi

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

  # A bundled .env is written alongside the real one rather than over it —
  # clobbering a working .env on the target is not something to do silently.
  if [ -f "${stage}/env" ]; then
    local dest="${REPO_ROOT}/.env.imported"
    # chmod after the copy, not umask before it: cp carries the source file's
    # mode across, and on some hosts (Synology w/ ACLs) that's world-readable.
    cp "${stage}/env" "${dest}"
    chmod 600 "${dest}"
    echo ""
    log "Bundle included a .env — written to ${dest} (mode 0600)."
    log "Review it, then:  mv ${dest} ${REPO_ROOT}/.env"
  fi

  echo ""
  success "Import complete. Remaining steps:"
  echo "  1. Ensure .env is in place    ->  ./scripts/mai-tai-config.sh check-env"
  echo "  2. Restart the stack          ->  ./dev.sh local up"

  # Only nag about re-entering credentials when the bundle actually dropped
  # them; a full bundle carries them and the target is ready to go.
  local had_secrets
  had_secrets="$(python3 -c \
    "import json;print(json.load(open('${stage}/manifest.json')).get('contains_secrets',False))" \
    2>/dev/null || echo False)"
  if [ "${had_secrets}" != "True" ]; then
    echo "  3. Re-enter credentials in Settings > AI (this bundle was scrubbed)"
    echo ""
    log "Users needing credentials re-entered:"
    psql_q "select '  - ' || email from users order by email" || true
  else
    echo ""
    log "Credentials came across with the bundle — nothing to re-enter."
    warn "Delete ${bundle} now that the move is done; it holds live secrets."
  fi
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
  sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

case "${1:-}" in
  export)    shift; cmd_export "$@" ;;
  import)    shift; cmd_import "$@" ;;
  inspect)   shift; cmd_inspect "$@" ;;
  check-env) shift; cmd_check_env "$@" ;;
  ""|-h|--help|help) usage ;;
  *) error "Unknown command: $1"; echo ""; usage; exit 1 ;;
esac
