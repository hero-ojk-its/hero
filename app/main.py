from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db, seed_initial_categories, SessionLocal

# IMPORT EXPLICIT
from app.routers.auth import router as auth_router
from app.routers.audit import router as audit_router
from app.routers.categories import router as categories_router
from app.routers.ingest import router as ingest_router
from app.routers.documents import router as documents_router
from app.routers.internal import router as internal_router  
from app.routers.scraping_sources import router as scraping_sources_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try: seed_initial_categories(db)
    finally: db.close()
    yield

app = FastAPI(title="HERO Backend API", version="0.1.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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