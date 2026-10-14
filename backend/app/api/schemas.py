"""Pydantic request/response models for the HTTP API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    expires_at: datetime


class ActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = Field(max_length=100)
    params: dict[str, Any]
    idempotency_key: str = Field(min_length=8, max_length=100)
    rationale: str = Field(default="", max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)


class ActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proposed_by: str
    tool: str
    params: dict[str, Any]
    tier: str
    status: str
    rationale: str
    evidence_ids: list[str]
    idempotency_key: str
    decided_by: int | None
    decided_at: datetime | None
    result: dict[str, Any] | None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    ts: datetime
    actor: str
    event_type: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str


class VerifyOut(BaseModel):
    ok: bool
    checked: int
    broken_at_seq: int | None
    reason: str | None


class UploadOut(BaseModel):
    rows: int
    inserted: int
    skipped_duplicates: int
    linked: int
    by_rule: int
    by_llm: int
    needs_review: int
