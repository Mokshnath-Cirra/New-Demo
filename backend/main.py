"""AURA AI - FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api import assets, auth, metrics, telemetry
from backend.config import settings
from backend.database import SessionLocal, init_db
from backend.services.ml_service import MLService
from backend.services.rate_limiter import SlidingWindowLimiter
from backend.services.seed import seed_database

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] [%(levelname)s] [%(module)s]: %(message)s")
logger = logging.getLogger("aura")
PREDICT_PATH = "/api/predict"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app.state.ml = MLService(settings.ARTIFACT_DIR)
    app.state.ml.load()
    app.state.limiter = SlidingWindowLimiter(settings.RATE_LIMIT_PREDICT_PER_MIN)
    async with SessionLocal() as db:
        await seed_database(db, app.state.ml)
    logger.info("AURA AI ready (model loaded: %s)", app.state.ml.loaded)
    yield


app = FastAPI(title="AURA AI - Fleet & Machinery Health Suite", version="1.0.0", lifespan=lifespan)
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    if request.url.path == PREDICT_PATH and request.method == "POST":
        client = request.client.host if request.client else "unknown"
        if not request.app.state.limiter.allow(client):
            return JSONResponse(status_code=429, content={
                "status": "error", "error_code": "RATE_LIMITED",
                "message": "Too many evaluations. Wait a moment and try again."})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    err = exc.errors()[0]
    field = ".".join(str(p) for p in err["loc"] if p != "body")
    return JSONResponse(status_code=422, content={
        "status": "error", "error_code": "INVALID_INPUT", "field": field,
        "message": f"{field or 'Request'}: {err['msg']}"})


@app.exception_handler(HTTPException)
async def http_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={
        "status": "error", "error_code": f"HTTP_{exc.status_code}", "message": str(exc.detail)})


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={
        "status": "error", "error_code": "INTERNAL_ERROR",
        "message": "Something went wrong on the server. The incident was logged."})


@app.get("/api/health", tags=["system"])
async def health(request: Request):
    return {"status": "ok", "model_loaded": request.app.state.ml.loaded,
            "environment": settings.ENVIRONMENT}


for module in (auth, assets, telemetry, metrics):
    app.include_router(module.router)

if settings.FRONTEND_DIR.exists():  # lets `python run.py` serve the UI without NGINX
    app.mount("/", StaticFiles(directory=settings.FRONTEND_DIR, html=True), name="frontend")
