"""Main FastAPI entrypoint for AquaShift backend."""
import logging
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api import api_router
from backend.app.core.config import settings
from backend.app.optimizer import OptimizationValidationException

logger = logging.getLogger("aquashift")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AquaShift — Water-constrained crop planning and diversification decision simulator.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Structured Error Handlers (Zero Traceback Leakage)
# -----------------------------------------------------------------------------

@app.exception_handler(OptimizationValidationException)
async def optimization_validation_handler(
    request: Request,
    exc: OptimizationValidationException,
) -> JSONResponse:
    """Handle pre-solve optimization hard-constraint validation failures."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Optimization Validation Error",
            "error_code": exc.error_code,
            "message": exc.message,
            "conflicting_constraints": exc.conflicting_constraints,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle Pydantic request schema validation failures with informative messages."""
    errors = []
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err.get("loc", []))
        errors.append({
            "field": field,
            "message": err.get("msg", "Invalid value"),
            "type": err.get("type", "value_error"),
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "message": "Invalid input parameters. Please check field requirements and bounds.",
            "detail": errors,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle standard HTTP exceptions with structured response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP Error",
            "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled internal errors without leaking Python tracebacks to clients."""
    logger.error("Unhandled internal server error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred during processing.",
        },
    )


# Include API routes
app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/", tags=["Root"])
async def root():
    """Root redirect / information endpoint."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": f"{settings.API_PREFIX}/health",
        "config": f"{settings.API_PREFIX}/config",
        "baseline": f"{settings.API_PREFIX}/baseline",
    }
