# Contributing to Mai-Tai

Thanks for your interest in contributing! This guide covers everything you need to get started.

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/jmcdice/mai-tai-dev.git
cd mai-tai-dev

# 2. Set up environment
cp .env.example .env

# 3. Start local development
./dev.sh local up

# 4. Open the app
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
```

## Development Workflow

### 1. Create a Branch

Always work on a feature branch:

```bash
git checkout main && git pull
git checkout -b feature/your-feature-name
```

Branch naming:
- `feature/` - New functionality
- `fix/` - Bug fixes
- `docs/` - Documentation only
- `refactor/` - Code improvements

### 2. Make Changes

**Frontend** (Next.js, TypeScript, Tailwind):
```bash
cd frontend
npm run dev    # Hot reload on http://localhost:3000
npm run lint   # Type check
npm run build  # Production build
```

**Backend** (FastAPI, Python, SQLAlchemy):
```bash
cd backend
ruff check .   # Lint
# Changes auto-reload with Docker
```

### 3. Test Locally

```bash
./dev.sh local rebuild  # Apply changes
./dev.sh local logs     # Watch logs
./dev.sh local status   # Check health
```

### 4. Commit

Use conventional commits:

```bash
git commit -m "feat: add workspace export feature"
git commit -m "fix: resolve WebSocket reconnection"
git commit -m "docs: update API examples"
```

| Prefix | When to Use |
|--------|-------------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation |
| `refactor:` | Code restructuring |
| `test:` | Tests |
| `chore:` | Tooling, deps |

**No emojis in commit messages.**

### 5. Push and Open PR

```bash
git push origin feature/your-feature-name

# Create PR via GitHub CLI
gh pr create --title "feat: your feature" --body "Description" --base main
```

### 6. CI Checks

Your PR will automatically run:

| Check | What It Does |
|-------|--------------|
| **Frontend Build** | TypeScript check + production build |
| **Backend Lint** | Ruff linting for Python |
| **Security Scan** | Trivy vulnerability scanner |
| **CodeQL** | Static security analysis |
| **GitGuardian** | Secret detection |

All checks must pass before merging.

### 7. Merge

Once approved:
```bash
gh pr merge --squash --delete-branch
```

## Code Style

### Frontend (TypeScript/React)

- TypeScript strict mode
- Mobile-first CSS (design for phones first)
- Use shadcn/ui components
- Follow existing patterns in `/components`

```typescript
// Good: explicit types, mobile-first
interface Props {
  workspace: Workspace;
  onSelect: (id: string) => void;
}

export function WorkspaceCard({ workspace, onSelect }: Props) {
  return (
    <div className="p-4 md:p-6">  {/* Mobile-first */}
      ...
    </div>
  );
}
```

### Backend (Python)

- Type hints required
- Async/await for DB operations
- PEP 8 style (enforced by ruff)

```python
# Good: typed, async
async def get_workspace(
    workspace_id: UUID,
    db: AsyncSession,
    user: User
) -> Workspace:
    ...
```

## Useful Commands

All development is done via `./dev.sh local`:

```bash
# Services
./dev.sh local up              # Start all services (frontend, backend, postgres)
./dev.sh local down            # Stop all services
./dev.sh local restart         # Restart all services
./dev.sh local rebuild         # Rebuild and restart all services
./dev.sh local logs            # Follow logs (or: ./dev.sh local logs backend)
./dev.sh local status          # Check service health

# Database
./dev.sh local migrate         # Run database migrations
./dev.sh local backup          # Backup database to SQL file
./dev.sh local restore         # Restore database from SQL file
./dev.sh local shell           # Open shell in container (default: backend)
./dev.sh local nuke-db         # Delete all database data and start fresh

# Nuclear option
./dev.sh local nuke-everything # ☢️ Wipe everything: containers, volumes, configs, MCP processes
```

## Reporting Issues

Please include:
- Steps to reproduce
- Expected vs actual behavior
- Browser/OS information
- Logs from `./dev.sh local logs`

## Security Issues

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

## Questions?

Open an issue with the `question` label or check existing discussions.

