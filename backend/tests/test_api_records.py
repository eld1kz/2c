"""Evidence records for the web UI (Phase 5): GET /records/{ref} and GET /records?ref=…"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Business, Invoice, Role, User
from seed.load import DEMO_PASSWORD
from tests.test_api import _login, client, db  # noqa: F401 - fixtures


def _invoice_id(db, number: str) -> int:  # noqa: ANN001
    with db() as s:
        return s.scalar(select(Invoice.id).where(Invoice.number == number))


def test_records_need_a_signed_in_user(client: TestClient) -> None:  # noqa: F811
    assert client.get("/records/invoice:1").status_code == 401
    assert client.get("/records", params={"ref": ["invoice:1"]}).status_code == 401


def test_invoice_record_keeps_document_text_wrapped(client: TestClient, db) -> None:  # noqa: F811, ANN001
    ref = f"invoice:{_invoice_id(db, 'QS-2291')}"
    out = client.get(f"/records/{ref}", headers=_login(client, "viewer")).json()
    assert out["ref"] == ref and out["kind"] == "invoice" and out["label"] == "QS-2291"
    notes = out["data"]["notes"]
    assert set(notes) == {"untrusted_text", "source"} and notes["untrusted_text"]
    assert all(set(ln["description"]) == {"untrusted_text", "source"} for ln in out["data"]["lines"])


def test_record_of_another_business_is_not_found(client: TestClient, db) -> None:  # noqa: F811, ANN001
    with db() as s:
        other = Business(name="Other Co", base_currency="USD", industry="x", min_cash_buffer=0, settings={})
        s.add(other)
        s.flush()
        s.add(User(business_id=other.id, email="owner@other.example", name="O", role=Role.owner,
                   password_hash=s.scalar(select(User.password_hash))))
        s.commit()
    token = client.post("/auth/login", json={"email": "owner@other.example", "password": DEMO_PASSWORD}).json()
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    ref = f"invoice:{_invoice_id(db, 'INV-1042')}"
    assert client.get(f"/records/{ref}", headers=headers).status_code == 404
    assert client.get("/records", params={"ref": [ref]}, headers=headers).json() == [{"ref": ref, "label": None}]


@pytest.mark.parametrize("ref", ["invoice", "invoice:abc", "INVOICE:1", "invoice:1:2", "x" * 40 + ":1"])
def test_malformed_refs_are_rejected(client: TestClient, ref: str) -> None:  # noqa: F811
    assert client.get(f"/records/{ref}", headers=_login(client, "viewer")).status_code == 422


def test_unknown_record_is_not_found(client: TestClient) -> None:  # noqa: F811
    assert client.get("/records/invoice:999999", headers=_login(client, "viewer")).status_code == 404
    assert client.get("/records/forecast_week:6", headers=_login(client, "viewer")).status_code == 404


def test_labels_for_many_refs(client: TestClient, db) -> None:  # noqa: F811, ANN001
    ref = f"invoice:{_invoice_id(db, 'INV-1042')}"
    out = client.get("/records", params={"ref": [ref, "invoice:999999", "nope:1"]}, headers=_login(client, "viewer"))
    assert out.json() == [{"ref": ref, "label": "INV-1042"}, {"ref": "invoice:999999", "label": None},
                          {"ref": "nope:1", "label": None}]
    too_many = client.get("/records", params={"ref": [ref] * 51}, headers=_login(client, "viewer"))
    assert too_many.status_code == 422
