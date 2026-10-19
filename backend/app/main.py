from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api import (routes_actions, routes_afford, routes_audit, routes_auth, routes_chat, routes_dashboard,
                     routes_demo, routes_memo, routes_paperwork, routes_records, routes_team,
                     routes_today, routes_transactions, routes_upload, routes_whatif)
from app.config import check_jwt_secret, check_production, get_settings

settings = get_settings()
check_jwt_secret(settings)
check_production(settings)

# No interactive docs or schema in production (the backend is not public there anyway).
docs = {"docs_url": None, "redoc_url": None, "openapi_url": None} if settings.is_production else {}
app = FastAPI(title="Ledgerwise", **docs)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
for router in (routes_auth.router, routes_actions.router, routes_audit.router, routes_upload.router,
               routes_chat.router, routes_dashboard.router, routes_records.router, routes_transactions.router,
               routes_demo.router, routes_whatif.router, routes_memo.router, routes_paperwork.router,
               routes_today.router, routes_afford.router, routes_team.router):
    app.include_router(router)


@app.exception_handler(RequestValidationError)
def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """422 without echoing the submitted values (untrusted, and possibly not even valid JSON, e.g. NaN)."""
    errors = [{"loc": list(e.get("loc", ())), "msg": str(e.get("msg", "")), "type": e.get("type", "")}
              for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


class Health(BaseModel):
    status: str


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok")
