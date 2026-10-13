import pytest
from fastapi.testclient import TestClient

from app.config import Settings, check_jwt_secret

from app.main import app


def test_health() -> None:
    assert TestClient(app).get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("secret", ["", "CHANGE_ME", "x" * 31])
def test_weak_jwt_secret_refuses_boot(secret: str) -> None:
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        check_jwt_secret(Settings(jwt_secret=secret))


def test_strong_jwt_secret_accepted() -> None:
    check_jwt_secret(Settings(jwt_secret="x" * 32))
