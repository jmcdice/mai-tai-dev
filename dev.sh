#!/usr/bin/env bash
set -e

# mai-tai development script
# Library files are in lib/

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source library modules
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/local.sh"

# Main command router
case "$1" in
    local)
        shift
        local_cmd "$@"
        ;;
    *)
        echo "mai-tai development script"
        echo ""
        echo "Usage: ./dev.sh local <command>"
        echo ""
        echo "Commands:"
        echo "  up              Start all services (frontend, backend, postgres)"
        echo "  down            Stop all services"
        echo "  restart         Restart all services"
        echo "  rebuild         Rebuild and restart all services"
        echo "  logs            View logs (optionally: ./dev.sh local logs backend)"
        echo "  status          Check service health"
        echo "  backup          Backup database to SQL file"
        echo "  restore         Restore database from SQL file"
        echo "  migrate         Run database migrations"
        echo "  shell           Open shell in container (default: backend)"
        echo "  nuke-db         Delete all database data and start fresh"
        echo "  nuke-everything ☢️  Wipe everything: containers, volumes, configs, MCP processes"
        echo ""
        echo "Examples:"
        echo "  ./dev.sh local up       # Start everything"
        echo "  ./dev.sh local logs     # Follow all logs"
        echo "  ./dev.sh local backup   # Backup database"
        ;;
esac

