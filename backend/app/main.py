from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api import routes_actions, routes_audit, routes_auth, routes_upload
from app.config import check_jwt_secret, get_settings

settings = get_settings()
check_jwt_secret(settings)

app = FastAPI(title="Ledgerwise")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
for router in (routes_auth.router, routes_actions.router, routes_audit.router, routes_upload.router):
    app.include_router(router)


class Health(BaseModel):
    status: str


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok")
