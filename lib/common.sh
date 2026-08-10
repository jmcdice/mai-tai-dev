#!/usr/bin/env bash
# Common utilities for dev.sh

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    if [ "${DEBUG:-}" = "1" ]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

# Secrets worth generating for a brand new install, and how to make each one.
GENERATED_SECRETS="POSTGRES_PASSWORD SECRET_KEY ENCRYPTION_KEY NEXTAUTH_SECRET"

gen_secret() {
    case "$1" in
        # Fernet wants exactly 32 url-safe-base64 bytes, padding included.
        ENCRYPTION_KEY) openssl rand -base64 32 | tr '+/' '-_' ;;
        # Alphanumeric only: this one ends up in a DATABASE_URL, where a
        # stray '/' or '@' would silently truncate the connection string.
        POSTGRES_PASSWORD) openssl rand -base64 36 | tr -dc 'A-Za-z0-9' | head -c 32 ;;
        *) openssl rand -base64 32 ;;
    esac
}

# Rewrite "KEY=" in place, leaving the surrounding comments alone.
set_env_var() {
    local key="$1" value="$2"
    # '|' as the delimiter, since base64 contains '/' but never '|'.
    sed -i.bak "s|^${key}=.*|${key}=${value}|" .env && rm -f .env.bak
}

read_env_var() {
    sed -n "s|^$1=||p" .env | head -1
}

# Make sure .env exists and can actually boot the stack.
#
# The example ships its secrets blank on purpose — a shipped default password
# is a password everybody already knows. So a brand new .env gets real
# randomness written into it here, rather than making the operator hand-edit a
# file before anything works.
#
# An .env that already exists is only ever *read*. Filling in its blanks would
# be actively destructive: an empty ENCRYPTION_KEY is a supported state that
# means "derive it from SECRET_KEY", and writing a fresh one there would make
# every secret already encrypted at rest permanently unreadable.
check_env() {
    if [ -f .env ]; then
        if [ -z "$(read_env_var POSTGRES_PASSWORD)" ]; then
            log_error "POSTGRES_PASSWORD is empty in .env — nothing will start without it."
            log_error "Generate one with:"
            log_error "    openssl rand -base64 36 | tr -dc 'A-Za-z0-9' | head -c 32"
            log_error "If this database already has data, you need its existing password, not a new one."
            exit 1
        fi
        if [ -z "$(read_env_var SECRET_KEY)" ]; then
            log_warn "SECRET_KEY is empty in .env; falling back to a well-known default."
            log_warn "Fine for a scratch install, not fine for anything you care about."
        fi
        return
    fi

    if [ ! -f .env.example ]; then
        log_error ".env.example not found — are you running this from the repo root?"
        exit 1
    fi
    if ! command -v openssl > /dev/null 2>&1; then
        log_error "openssl is not installed, so I can't generate the secrets a new install needs."
        log_error "Install openssl, or write these into .env by hand: $GENERATED_SECRETS"
        exit 1
    fi

    log_warn "No .env found — setting up a fresh install."
    cp .env.example .env
    chmod 600 .env
    for key in $GENERATED_SECRETS; do
        [ -z "$(read_env_var "$key")" ] && set_env_var "$key" "$(gen_secret "$key")"
    done
    log_info "Created .env with generated secrets:$(printf ' %s' $GENERATED_SECRETS)"
    log_warn "Those are real credentials now. .env is gitignored and chmod 600 — keep it that way."
}

# Poll until a command succeeds, or give up with something the operator can act on.
#
# These loops used to be unbounded, so any failure that isn't "still booting"
# (a crash-looping container, a port already taken) looked identical to a slow
# start: a cursor blinking forever.
wait_for() {
    local what="$1" timeout="$2"
    shift 2
    local waited=0
    until "$@" > /dev/null 2>&1; do
        if [ "$waited" -ge "$timeout" ]; then
            log_error "$what did not come up within ${timeout}s."
            log_error "Last 30 lines:"
            docker compose -f "${COMPOSE_FILE:-docker-compose.yml}" logs --tail=30 2>&1 | sed 's/^/    /'
            exit 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
}

# Get the script directory (where dev.sh lives)
get_script_dir() {
    cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

