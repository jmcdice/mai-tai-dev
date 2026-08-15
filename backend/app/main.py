import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import select

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.services.scheduler import run_scheduler
from app.services.watchdog import run_watchdog

logger = logging.getLogger(__name__)

settings = get_settings()

# Rate limiter - uses in-memory storage by default
# For multi-instance deployments, configure Redis: storage_uri="redis://host:port"
limiter = Limiter(key_func=get_remote_address)


async def _reap_orphaned_agents() -> None:
    """Reconcile agent containers against the workspaces that should have them.

    Two ways a container outlives its reason to exist:

    Deleted workspaces. Deletion now stops the agent first, but that only helps
    from here on: containers stranded before the fix — or by a backend that
    died mid-delete — stay up under `restart: unless-stopped` and poll a
    workspace that no longer exists. These are removed, memory volume included.

    Archived workspaces. Archiving now stops the agent too, with the same
    caveat for anything archived earlier. These are stopped but their memory
    volume is KEPT, because unarchive restores from it. This is the invisible
    case: an archived workspace is filtered out of every listing, so its
    runaway agent is the one nobody notices.
    """
    if not settings.agent_reaper_enabled:
        return

    from app.db.session import AsyncSessionLocal
    from app.models.workspace import Workspace
    from app.services.agents import reap_orphaned_agents, stop_archived_agents

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Workspace.id, Workspace.archived))
            rows = result.all()
        live_ids = {str(row[0]) for row in rows}
        archived_ids = {str(row[0]) for row in rows if row[1]}

        reaped = await asyncio.to_thread(reap_orphaned_agents, live_ids)
        if reaped:
            logger.info("Reaped %d orphaned agent container(s): %s", len(reaped), ", ".join(reaped))

        stopped = await asyncio.to_thread(stop_archived_agents, archived_ids)
        if stopped:
            logger.info(
                "Stopped %d agent container(s) for archived workspace(s): %s",
                len(stopped),
                ", ".join(stopped),
            )
    except Exception:
        # Never let reconciliation keep the API from coming up.
        logger.exception("Orphaned agent reconciliation failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Reconcile stray agent containers, then run the background loops.

    Two loops, separately switchable: the scheduler fires due tasks, the
    watchdog restarts agents that have gone silent. Independent flags because
    they fail independently — a deployment debugging a restart loop wants the
    watchdog off without losing its cron jobs.
    """
    await _reap_orphaned_agents()

    stop_event = asyncio.Event()
    tasks = []
    if settings.scheduler_enabled:
        tasks.append(asyncio.create_task(run_scheduler(stop_event)))
    if settings.watchdog_enabled:
        tasks.append(asyncio.create_task(run_watchdog(stop_event)))

    yield

    stop_event.set()
    for task in tasks:
        await task


app = FastAPI(
    title="mai-tai API",
    description="Backend API for mai-tai agent collaboration platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Attach limiter to app state so it can be accessed in route modules
app.state.limiter = limiter


# Custom rate limit exceeded handler with JSON response
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": f"Too many requests. {exc.detail}",
        },
    )


# Build CORS origins list
if settings.cors_allow_all:
    # Allow all origins in development mode (for LAN testing)
    # Note: When allow_credentials=True, we cannot use "*" for origins
    # Instead, we set allow_credentials=False when using wildcard
    cors_origins = ["*"]
    cors_allow_credentials = False
else:
    cors_origins = list(settings.cors_origins_list)
    if settings.extra_cors_origin:
        cors_origins.append(settings.extra_cors_origin)
    cors_allow_credentials = True

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(v1_router)


@app.get("/")
async def root():
    return {"message": "mai-tai API", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}

