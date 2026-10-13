from fastapi import FastAPI
from pydantic import BaseModel

from app.config import check_jwt_secret, get_settings

check_jwt_secret(get_settings())

app = FastAPI(title="Ledgerwise")


class Health(BaseModel):
    status: str


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok")
