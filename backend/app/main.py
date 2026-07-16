import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.services.scheduler import run_scheduler

settings = get_settings()

# Rate limiter - uses in-memory storage by default
# For multi-instance deployments, configure Redis: storage_uri="redis://host:port"
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the workspace task scheduler for the app's lifetime."""
    if not settings.scheduler_enabled:
        yield
        return
    stop_event = asyncio.Event()
    scheduler_task = asyncio.create_task(run_scheduler(stop_event))
    yield
    stop_event.set()
    await scheduler_task


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

