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
- [ ] **3. Remove leftover "free trial" language** -- NOT FOUND in current codebase. Joey may have already cleaned this up. Verify by running the app and checking the landing page visually.

### Medium Priority -- UX Confusion

- [x] **4. Default Dude Mode to off** -- ALREADY DONE. Backend sets `dude_mode: False` on workspace creation for both email/password and OAuth registration (`backend/app/api/v1/auth.py` lines 98 and 326). Michael's confusion was likely from an earlier version or from not understanding what "the Dude" was, not from it being on by default.
- [ ] **5. Add "100% local" messaging in the UI** -- The landing page already has "100% local. Runs entirely on your machine. No data leaves your network." but the registration page has nothing. Add local-only messaging to the registration/login flows where trust matters most.

### Lower Priority

- [ ] **6. IP concerns with The Dude character** -- Trademarked character (Big Lebowski) could be a problem if this goes commercial. Noting for awareness, not actionable in this PR.

## Code Investigation Notes

- Dude Mode toggle is in `WorkspaceSettings.tsx` under "Agent Personality" section
- When enabled: agent name becomes "His Dudeness", avatar changes to `/the-dude-avatar.png`, tone instruction prepended in `backend/app/api/v1/mcp.py`
- Registration creates default workspace with `settings={"dude_mode": False}`
- Landing page already has some good "100% local" messaging in the lower CTA section
