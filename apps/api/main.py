from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import get_settings
from apps.api.database.session import SessionLocal, engine
from apps.api.models import Base
from apps.api.routes import audit, auth, dashboard, documents, jobs, notifications, policies, printers, reports, rules, settings as settings_routes, tokens, users
from apps.api.services.seed import run_all_seeds

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        run_all_seeds(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="SecurePrint API",
    description="Web-based Automated Document Classification and Data Loss Prevention System for Printed Documents",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"

    path = request.url.path
    if "/jobs/" in path and path.endswith("/document"):
        origins = " ".join(settings.cors_origins)
        response.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {origins}"
    else:
        response.headers["X-Frame-Options"] = "DENY"

    return response


app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(audit.router)
app.include_router(rules.router)
app.include_router(policies.router)
app.include_router(printers.router)
app.include_router(users.router)
app.include_router(dashboard.router)
app.include_router(settings_routes.router)
app.include_router(tokens.router)
app.include_router(notifications.router)
app.include_router(reports.router)


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "app": settings.app_name}
