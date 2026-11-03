"""
Ponto de entrada principal da aplicação FastAPI (PST Viewer).
Registra todas as rotas de API, arquivos estáticos e a interface web inspirada no Outlook.
"""

from __future__ import annotations

from pathlib import Path
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.api.routes_admin import router as admin_router
from app.api.routes_auth import router as auth_router
from app.api.routes_export import router as export_router
from app.api.routes_reader import router as reader_router
from app.api.routes_search_attachments import router as search_att_router
from app.api.routes_sessions import router as sessions_router
from app.core.config import settings
from app.database.session import get_db, verify_mysql_connection

BASE_APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_APP_DIR / "templates"
STATIC_DIR = BASE_APP_DIR / "static"

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next) -> Response:
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer"
    if "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    if "Content-Security-Policy" not in response.headers:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob: https: http:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "frame-src 'self' data: blob:; "
            "frame-ancestors 'self'; "
            "form-action 'self'; "
            "connect-src 'self';"
        )
    return response


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(reader_router)
app.include_router(search_att_router)
app.include_router(export_router)
app.include_router(admin_router)


@app.get("/", response_class=HTMLResponse)
def serve_outlook_spa() -> HTMLResponse:
    index_file = TEMPLATES_DIR / "index.html"
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    db_info = verify_mysql_connection(db)
    return {
        "status": "ok",
        "database_engine": "mysql_innodb",
        "database_version": db_info["version"],
    }
