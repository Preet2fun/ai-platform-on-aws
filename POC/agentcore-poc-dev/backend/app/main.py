# app/main.py
"""
FastAPI main application.
Entry point for the MSP Assistant API backend.
"""

import asyncio
import os
import uuid
import contextvars
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings
from app.core.task_registry import cancel_all_tasks
from app.api import routes
import logging
from pythonjsonlogger import jsonlogger

# --- Structured JSON Logging ---
# Correlation ID stored in contextvars — accessible from any log call in the request
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class CorrelatedJsonFormatter(jsonlogger.JsonFormatter):
    """JSON log formatter that injects request_id into every log line."""
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["request_id"] = request_id_ctx.get("-")
        log_record["level"] = record.levelname
        log_record["logger"] = record.name


def _configure_logging():
    """Configure structured JSON logging for all loggers."""
    handler = logging.StreamHandler()
    formatter = CorrelatedJsonFormatter(
        fmt="%(asctime)s %(level)s %(logger)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    # --- Startup ---
    logger.info("MSP Assistant API starting up")
    logger.info("Region: %s", settings.AWS_REGION)
    logger.info("Cognito User Pool: %s", settings.COGNITO_USER_POOL_ID)
    logger.info("Model: %s", settings.MODEL)

    # PRELOAD MCP clients at startup for fast first response
    try:
        logger.info("Preloading MCP clients")
        from app.core.shared_mcp_client import SharedMCPClient
        SharedMCPClient.initialize()
        logger.info("MCP clients preloaded successfully")
    except Exception as e:
        logger.warning("MCP preloading warning: %s", e)
        # Continue startup even if MCP fails - will lazy load later

    logger.info("Application ready")
    
    yield  # Application runs here
    
    # --- Shutdown ---
    logger.info("MSP Assistant API shutting down")
    await cancel_all_tasks()


# Create FastAPI app
_is_dev = os.getenv("ENVIRONMENT", "production") != "production"
app = FastAPI(
    title="MSP Assistant API",
    description="Backend API for AWS MSP Smart Agent Assist",
    version="2.0.0",
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    lifespan=lifespan,
)

# CORS middleware for local development and production
allowed_origins = []

# In production, only allow the configured frontend
if settings.FRONTEND_URL:
    allowed_origins.append(settings.FRONTEND_URL)

# Add localhost origins only when no FRONTEND_URL is set (local dev)
if not settings.FRONTEND_URL or "localhost" in settings.FRONTEND_URL:
    allowed_origins.extend(["http://localhost:5173", "http://localhost:3000"])
    # Do NOT add http:// version — all prod traffic must use HTTPS

# Pin CORS regex to the specific CloudFront distribution if known, otherwise allow all
# CloudFront distributions as a fallback (e.g. first deploy before CLOUDFRONT_DOMAIN is set).
# Security note: the fallback allows any CloudFront distribution — replace with the
# pinned regex once CLOUDFRONT_DOMAIN is populated by deploy.sh.
if settings.CLOUDFRONT_DOMAIN:
    import re as _re
    # re.escape converts dots/hyphens in the domain to literal regex characters,
    # preventing a domain like "d1abc.cloudfront.net" from accidentally matching
    # "d1abcXcloudfrontYnet" due to unescaped regex metacharacters.
    _escaped = _re.escape(settings.CLOUDFRONT_DOMAIN)
    # Anchor to https:// only — no http:// variant; CloudFront always serves HTTPS.
    _origin_regex = rf"https://{_escaped}"
else:
    # FALLBACK: allows any CloudFront distribution — safe until CLOUDFRONT_DOMAIN is exported.
    # Pattern requires lowercase alphanumeric subdomain + literal ".cloudfront.net" over HTTPS,
    # which limits exposure to the CloudFront namespace while still supporting fresh deploys
    # where the specific distribution ID is not yet known.
    _origin_regex = r"https://[a-z0-9]+\.cloudfront\.net"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Accept", "Cache-Control"],
    expose_headers=["Content-Type", "X-Request-Id"],
    max_age=600  # Cache preflight requests for 10 minutes
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Append hardened security headers to every outbound HTTP response.

    Applied globally so that all routes — including error responses and
    redirects — carry these headers without requiring per-route decoration.

    Headers set and their purpose:
        X-Content-Type-Options: nosniff
            Prevents browsers from MIME-sniffing a response away from the
            declared Content-Type, closing a class of content-injection attacks.
        X-Frame-Options: DENY
            Blocks the API from being embedded in any <frame> or <iframe>,
            mitigating clickjacking.  Redundant with the CSP frame-ancestors
            directive below, but kept for older browser compatibility.
        Strict-Transport-Security: max-age=31536000; includeSubDomains
            Instructs browsers to use HTTPS for all requests to this origin
            for one year, including subdomains.  Only meaningful when the API
            is served over HTTPS (i.e., production behind CloudFront/ALB).
        Content-Security-Policy: default-src 'self'; frame-ancestors 'none'
            Restricts resource loading to the same origin and reaffirms no
            framing is permitted.
        Referrer-Policy: strict-origin-when-cross-origin
            Sends full referrer on same-origin requests; only the origin on
            cross-origin HTTPS→HTTPS; nothing on HTTPS→HTTP.
        Permissions-Policy: camera=(), microphone=(), geolocation=()
            Explicitly disables browser feature APIs that this API does not need,
            reducing the attack surface if a page ever embeds this origin.
    """
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


app.add_middleware(SecurityHeadersMiddleware)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generate a unique request ID for each request and store in contextvars.
    
    The ID is:
    - Set in contextvars so all log lines in the request include it
    - Returned in the X-Request-Id response header for client-side correlation
    """
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        request_id_ctx.set(rid)
        response: Response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response


app.add_middleware(RequestIdMiddleware)

# --- Rate Limiting ---
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include API routes
app.include_router(routes.router, prefix=f"/api/{settings.API_VERSION}")

# Configure OpenTelemetry (only activates if OTEL_ENABLED=true)
from app.core.telemetry import configure_telemetry
configure_telemetry(app)

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "MSP Assistant API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }

# Health check endpoint (no authentication required)
@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring.
    Returns API status and version.
    """
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": "2.0.0",
        "cognito_configured": bool(settings.COGNITO_USER_POOL_ID),
        "model": settings.MODEL
    }

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle uncaught exceptions gracefully."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
