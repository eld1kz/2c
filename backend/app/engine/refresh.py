"""Recompute everything derived from the ledger: series, stats, base forecast, insights."""

from datetime import date

from sqlalchemy.orm import Session

from app.engine.counterparty_stats import refresh_counterparty_stats
from app.engine.forecast import project, save_forecast
from app.engine.insights.registry import refresh_insights
from app.engine.recurring import detect_recurring
from app.engine.snapshot import load_snapshot


def refresh_engine(session: Session, business_id: int, today: date) -> None:
    detect_recurring(session, business_id, today)
    refresh_counterparty_stats(session, business_id)
    snapshot = load_snapshot(session, business_id, today)
    forecast = project(snapshot)
    save_forecast(session, business_id, forecast)
    refresh_insights(session, snapshot, forecast)
