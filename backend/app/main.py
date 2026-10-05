import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, OperationalError

from app.config import settings, APP_VERSION
from app.database import seed_initial_categories, SessionLocal

# IMPORT EXPLICIT
from app.routers.auth import router as auth_router
from app.routers.audit import router as audit_router
from app.routers.categories import router as categories_router
from app.routers.ingest import router as ingest_router
from app.routers.documents import router as documents_router
from app.routers.internal import router as internal_router  
from app.routers.scraping_sources import router as scraping_sources_router
from app.routers.dashboard import router as dashboard_router
from app.routers.scans import router as scans_router
from app.routers.naming import router as naming_router

logger = logging.getLogger("hero")


def check_storage_writable(storage_path: str) -> bool:
    """Uji tulis-hapus berkas kecil di direktori .tmp penyimpanan."""
    try:
        tmp_dir = os.path.join(storage_path, ".tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        test_file = os.path.join(tmp_dir, f".health_{os.getpid()}.tmp")
        with open(test_file, "w") as f:
            f.write("ok")
        if os.path.exists(test_file):
            os.remove(test_file)
        return True
    except Exception:
        return False


def check_crawler_loaded(backend_name: str) -> bool:
    """Uji keberhasilan pemuatan crawler backend."""
    try:
        if backend_name == "push":
            return True
        from app.crawlers.registry import get_crawler
        crawler = get_crawler(settings)
        return crawler is not None
    except Exception:
        return False


def get_alembic_status(db):
    """Mendapatkan revisi Alembic DB dan Head script."""
    db_rev = None
    head_rev = None
    up_to_date = False
    try:
        res = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
        db_rev = res
    except Exception:
        db_rev = None

    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        head_rev = script.get_current_head()
    except Exception:
        head_rev = None

    if db_rev and head_rev and db_rev == head_rev:
        up_to_date = True
    elif not db_rev and not head_rev:
        up_to_date = True

    return db_rev, head_rev, up_to_date


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validasi konfigurasi produksi yang ketat saat startup
    if settings.app_env.lower() == "production":
        settings.validate_production_config()

    # Peringatan keamanan untuk internal_api_key jika bukan mode development
    if settings.app_env != "development":
        default_keys = ("change-me", "ganti-dengan", "change-me-internal-key")
        if any(settings.internal_api_key.lower().startswith(prefix) for prefix in default_keys):
            logger.critical(
                "PERINGATAN KEAMANAN KRITIS: 'INTERNAL_API_KEY' masih menggunakan nilai default di environment non-development (%s)! "
                "Harap segera perbarui kunci API internal ini sebelum rilis ke production.",
                settings.app_env,
            )

    db = SessionLocal()
    try:
        try:
            seed_initial_categories(db)
        except (ProgrammingError, OperationalError):
            logger.warning("Tabel belum ada. Jalankan 'alembic upgrade head' terlebih dahulu.")

        try:
            from app.services.source_runner import recover_stuck_folder_jobs
            recover_stuck_folder_jobs(db)
        except Exception as exc:
            logger.warning("Gagal memulihkan job sinkron_folder saat startup: %s", exc)

        try:
            from app.services.scan_service import recover_stuck_scan_sessions
            recover_stuck_scan_sessions(db, stuck_minutes=settings.scan_stuck_minutes, is_startup=True)
        except Exception as exc:
            logger.warning("Gagal memulihkan sesi pemindaian saat startup: %s", exc)
    finally:
        db.close()
    yield


# Tentukan visibilitas docs berdasarkan APP_ENV dan EXPOSE_API_DOCS
is_prod = settings.app_env.lower() == "production"
docs_url = None if (is_prod and not settings.expose_api_docs) else "/docs"
redoc_url = None if (is_prod and not settings.expose_api_docs) else "/redoc"
openapi_url = None if (is_prod and not settings.expose_api_docs) else "/openapi.json"

app = FastAPI(
    title="HERO Backend API",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
)


def custom_openapi():
    """Custom OpenAPI schema untuk memastikan upload file jamak dirender sebagai binary di Swagger UI."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )

    # Patch schemas pada components untuk file upload arrays
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    for schema_name, schema in schemas.items():
        if isinstance(schema, dict) and "properties" in schema:
            for prop_name, prop in schema["properties"].items():
                if isinstance(prop, dict) and prop.get("type") == "array" and "items" in prop:
                    items = prop["items"]
                    if isinstance(items, dict) and (items.get("type") == "string" or "contentMediaType" in items):
                        items["type"] = "string"
                        items["format"] = "binary"

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# CORS Configuration
raw_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if not raw_origins or "*" in raw_origins:
    cors_origins = ["*"]
    cors_allow_credentials = False
else:
    cors_origins = raw_origins
    cors_allow_credentials = True

class CustomCORSMiddleware(CORSMiddleware):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "Access-Control-Expose-Headers" in self.simple_headers:
            self.preflight_headers["Access-Control-Expose-Headers"] = self.simple_headers["Access-Control-Expose-Headers"]

app.add_middleware(
    CustomCORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length"],
)

# DAFTARKAN ROUTER
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(audit_router, prefix="/api/v1/audit-logs", tags=["Audit Logs"])
app.include_router(categories_router, prefix="/api/v1/categories", tags=["Categories"])
app.include_router(ingest_router, prefix="/api/v1/ingest", tags=["Ingest"])
app.include_router(documents_router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(internal_router, prefix="/api/v1/internal", tags=["Internal"])  
app.include_router(scraping_sources_router, prefix="/api/v1/scraping-sources", tags=["Scraping Sources"])  
app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(scans_router)  
app.include_router(naming_router)  


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok"}


@app.get("/health", tags=["Health"])
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.error("Health check failed on database: %s", exc)
        db_ok = False
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "degraded",
                "database": "error",
                "version": APP_VERSION,
                "app_env": settings.app_env,
            },
        )

    try:
        db_rev, head_rev, migrations_ok = get_alembic_status(db)
        storage_ok = check_storage_writable(settings.storage_path)
        crawler_loaded = check_crawler_loaded(settings.crawler_backend)
        protect_non_public = settings.protect_non_public_when_auth_disabled and not settings.auth_enabled

        overall_status = "ok" if (db_ok and migrations_ok) else "degraded"

        return {
            "status": overall_status,
            "database": "ok",
            "version": APP_VERSION,
            "app_env": settings.app_env,
            "alembic_revision": db_rev,
            "alembic_head": head_rev,
            "migrations_up_to_date": migrations_ok,
            "storage_writable": storage_ok,
            "crawler_backend": settings.crawler_backend,
            "crawler_loaded": crawler_loaded,
            "auth_enabled": settings.auth_enabled,
            "protect_non_public": protect_non_public,
        }
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