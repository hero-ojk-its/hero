import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, OperationalError

from app.config import settings
from app.database import seed_initial_categories, SessionLocal

# IMPORT EXPLICIT
from app.routers.auth import router as auth_router
from app.routers.audit import router as audit_router
from app.routers.categories import router as categories_router
from app.routers.ingest import router as ingest_router
from app.routers.documents import router as documents_router
from app.routers.internal import router as internal_router  
from app.routers.scraping_sources import router as scraping_sources_router

logger = logging.getLogger("hero")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        try:
            seed_initial_categories(db)
        except (ProgrammingError, OperationalError):
            logger.warning("Tabel belum ada. Jalankan 'alembic upgrade head' terlebih dahulu.")
    finally:
        db.close()
    yield


app = FastAPI(title="HERO Backend API", version="0.2.0", lifespan=lifespan)

# CORS Configuration
raw_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if not raw_origins or "*" in raw_origins:
    cors_origins = ["*"]
    cors_allow_credentials = False
else:
    cors_origins = raw_origins
    cors_allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DAFTARKAN ROUTER
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(audit_router, prefix="/api/v1/audit-logs", tags=["Audit Logs"])
app.include_router(categories_router, prefix="/api/v1/categories", tags=["Categories"])
app.include_router(ingest_router, prefix="/api/v1/ingest", tags=["Ingest"])
app.include_router(documents_router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(internal_router, prefix="/api/v1/internal", tags=["Internal"])  
app.include_router(scraping_sources_router, prefix="/api/v1/scraping-sources", tags=["Scraping Sources"])  


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok"}


@app.get("/health", tags=["Health"])
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "ok",
            "auth_enabled": settings.auth_enabled,
        }
    except Exception as exc:
        logger.error("Health check failed on database: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "database": "error"},
        )
    finally:
        db.close()


if settings.app_env == "development":
    @app.get("/debug-routes", tags=["Health"])
    def debug_routes():
        paths = []
        for route in app.routes:
            if hasattr(route, "path"):
                paths.append(route.path)
            elif hasattr(route, "routes"):
                for sub_route in route.routes:
                    if hasattr(sub_route, "path"):
                        paths.append(sub_route.path)
        return {"routes_terdaftar": paths}