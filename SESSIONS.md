# SESSIONS.md

Tracking feedback and work on this fork of [jmcdice/mai-tai-dev](https://github.com/jmcdice/mai-tai-dev).

## UX Feedback (from Michael Lipscombe conversation)

### High Priority -- Trust/Perception

- [ ] **1. Clarify that accounts are local-only** -- Registration page uses "Create your account", "Sign up", "or sign up with" language that implies a cloud service. Landing page has "Sign Up" and "Get Started" CTAs. Change wording to emphasize local-only. Key files:
  - `frontend/app/register/page.tsx` -- "Create your account" heading, "Create account" button, "or sign up with", "Signing up..."
  - `frontend/app/login/page.tsx` -- "Sign up" link
  - `frontend/app/(public)/landing/page.tsx` -- "Sign Up" nav button, "Get Started" CTAs
  - `README.md` -- "The first user to register..."
  - `lib/local.sh` -- "Register a new account"
- [ ] **2. Remove email requirement for local accounts** -- Email is currently the unique identifier for users and is used for login. Replacing with username is an architectural change (affects User model, auth flow, OAuth linking). Needs discussion on scope.
- [ ] **3. Remove leftover "free trial" language** -- NOT FOUND in current codebase (verified by full-text search). Joey may have already cleaned this up.

### Medium Priority -- UX Confusion

- [x] **4. Default Dude Mode to off** -- ALREADY DONE. Backend sets `dude_mode: False` on workspace creation for both email/password and OAuth registration (`backend/app/api/v1/auth.py`). Michael's confusion was likely from an earlier version or from not understanding what "the Dude" was.
- [ ] **5. Add "100% local" messaging in the UI** -- The landing page already has "100% local. Runs entirely on your machine. No data leaves your network." but the registration page has nothing. Add local-only messaging to the registration/login flows where trust matters most.

### Lower Priority

- [ ] **6. IP concerns with The Dude character** -- Trademarked character (Big Lebowski) could be a problem if this goes commercial. Noting for awareness, not actionable in this PR.

---

## Code Review Findings

### Critical -- Security

- [ ] **C1. OAuth endpoint accepts unverified identity claims** -- `backend/app/api/v1/auth.py` `/auth/oauth` endpoint trusts whatever `provider`, `oauth_id`, `email`, and `name` the client POSTs. No server-side verification of the OAuth token against GitHub/Google. Any client can forge identity claims and get tokens for any user. Account takeover is trivial.
- [ ] **C2. No password strength validation** -- `backend/app/schemas/auth.py` `UserCreate` and `PasswordChange` accept any non-empty string. No minimum length, no complexity check.
- [ ] **C3. Secret key defaults diverge across files** -- `config.py` checks for `"change-me-in-production-use-openssl-rand-hex-32"`, but `docker-compose.yml` defaults to `"change-me-in-production"` and `.env.example` uses a third value. The docker-compose default passes the production guard while being guessable.
- [ ] **C4. WebSocket tokens in URL query params** -- `backend/app/api/v1/websocket.py` and `frontend/hooks/use-websocket.ts`. JWT tokens and API keys appear in URLs (logs, browser history, Referer headers). Common WebSocket trade-off but worth documenting or mitigating with short-lived WS-specific tokens.

### Important -- Bugs/Design

- [ ] **I1. Zero working tests** -- `backend/tests/` is empty. Frontend has no test files or framework. `mcp-server/tests/test_completion_semantics.py` imports classes that no longer exist (stale from prior architecture).
- [ ] **I2. WebSocket auth broken for user-level API keys** -- `backend/app/api/v1/websocket.py` `validate_api_key()` does `str(api_key.workspace_id)` which becomes `"None"` for user-level keys. Comparison always fails. Needs the same owner-check logic as `get_api_key_auth` in `deps.py`.
- [ ] **I3. `datetime.utcnow()` mixed with `datetime.now(timezone.utc)`** -- Most models and endpoints use deprecated `datetime.utcnow()` (naive), but `security.py` and some endpoints use `datetime.now(timezone.utc)` (aware). Mixing naive and aware datetimes causes comparison bugs.
- [ ] **I4. `generate_api_key()` duplicated** -- Identical function in `backend/app/api/v1/auth.py` and `backend/app/api/v1/workspaces.py`. Should be in a shared module.
- [ ] **I5. Race condition in `_record_workspace_activity`** -- `backend/app/api/deps.py` does SELECT-then-INSERT (racy under concurrent requests). Docstring promises upsert (`INSERT ... ON CONFLICT DO UPDATE`) but doesn't implement it.
- [ ] **I6. First-user admin check loads all users into memory** -- `backend/app/api/v1/auth.py` does `select(User)` then `len(result.all())` instead of `COUNT` or `LIMIT 1`.
- [ ] **I7. No refresh token rotation or revocation** -- `backend/app/api/v1/auth.py` issues new refresh tokens but never invalidates old ones. Stolen tokens stay valid 30 days. No forced logout possible.
- [ ] **I8. Duplicate rate limiter instances** -- `main.py` and `auth.py` each create their own `Limiter()`. The `auth.py` limiter may not integrate with slowapi's request lifecycle since it's separate from `app.state.limiter`.
- [ ] **I9. Frontend 401 handler could loop** -- `frontend/lib/api.ts` redirects to `/` on 401 (except `/auth/me`). If root page makes any other authenticated call, redirect loops. Also creates a never-resolving promise (memory leak until navigation).
- [ ] **I10. `cors_allow_all` breaks IAP auth** -- `backend/app/main.py` disables credentials when `cors_allow_all=True`, but IAP mode uses `credentials: 'include'`. Deploying with both silently breaks auth.

### Minor -- Cleanup/Tech Debt

- [ ] **M1. Dead legacy aliases in `frontend/lib/api.ts`** -- ~15 "Legacy alias" functions and types for Project-to-Workspace migration that appear complete.
- [ ] **M2. API key `scopes` field defined but never enforced** -- `backend/app/models/api_key.py` has scopes column, no endpoint checks it.
- [ ] **M3. Message content mutated at read time** -- `backend/app/api/v1/mcp.py` `GET /mcp/messages` prepends formatting/tone/plan instructions to every user message. Original content is never returned as-is.
- [ ] **M4. Health endpoint doesn't check database** -- `backend/app/main.py` `/health` always returns healthy even if DB is down. Docker healthcheck uses this.
- [ ] **M5. Imports inside function bodies** -- `backend/app/api/v1/websocket.py` imports `asyncio`, `logging`, `hashlib`, `datetime` inside functions rather than at module level.
- [ ] **M6. `ConfigurationError` defined in two places** -- `mcp-server/mai_tai_mcp/config.py` and `mcp-server/mai_tai_mcp/errors.py` both define it.
- [ ] **M7. No DB connection pool tuning** -- `backend/app/db/session.py` uses SQLAlchemy defaults (pool_size=5). Fine for dev, bottleneck under load.
- [ ] **M8. Frontend has no automatic token refresh** -- Access token expires after 7 days, but the stored refresh token is never proactively used. User is silently logged out.

---

## Code Investigation Notes

- Dude Mode toggle is in `WorkspaceSettings.tsx` under "Agent Personality" section
- When enabled: frontend sets agent name to "His Dudeness" and avatar to `/the-dude-avatar.png` (in `workspaces/[id]/page.tsx`). Backend prepends tone instruction (in `backend/app/api/v1/mcp.py`).
- Registration creates default workspace with `settings={"dude_mode": False}`
- Landing page already has some good "100% local" messaging in the lower CTA section
