"""Human review of a transaction's category (SPEC §6.2): set it, and add a rule so the same payee or
description is categorized the same way next time.

Owner/accountant only, audited. Writes exactly two things: the transaction's categorization fields
(category, category_source = human, needs_review = False) and one CategoryRule. It never writes
counterparties, invoices, amounts, invoice links or anything else the payment gate reads; the derived
recurring series, forecast and insights are then recomputed (not counterparty payment stats).
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log as audit
from app.db.models import (
    Account,
    Category,
    CategoryRule,
    CategorySource,
    Counterparty,
    Role,
    RuleKind,
    RuleSource,
    Transaction,
    User,
)
from app.engine.categorize import direction_of
from app.engine.refresh import refresh_after_recategorize
from app.ingestion.normalizer import normalize
from app.services.action_service import Forbidden, NotFound, actor_for, utc_now

REVIEW_ROLES = (Role.owner, Role.accountant)
HUMAN_RULE_PRIORITY = 10  # ahead of seeded keyword (100+) and name (200+) rules


def _rule_for(session: Session, business_id: int, t: Transaction, category: Category) -> CategoryRule:
    counterparty = session.get(Counterparty, t.counterparty_id) if t.counterparty_id else None
    if counterparty is not None:
        kind, pattern = RuleKind.name, counterparty.normalized_name
    else:
        kind, pattern = RuleKind.keyword, normalize(t.raw_description)[:200]
    direction = direction_of(t.amount)
    rule = session.scalar(select(CategoryRule).where(
        CategoryRule.business_id == business_id, CategoryRule.source == RuleSource.human, CategoryRule.kind == kind,
        CategoryRule.pattern == pattern, CategoryRule.direction == direction))
    if rule is None:
        rule = CategoryRule(business_id=business_id, kind=kind, pattern=pattern, direction=direction, category=category,
                            source=RuleSource.human, priority=HUMAN_RULE_PRIORITY)
        session.add(rule)
    rule.category = category
    session.flush()
    return rule


def recategorize(session: Session, user: User, transaction_id: int, category: Category, today: date) -> Transaction:
    actor = actor_for(user).label
    base = {"business_id": user.business_id, "transaction_id": transaction_id}
    if user.role not in REVIEW_ROLES:
        audit.append(session, actor, "recategorize_forbidden", base | {"role": user.role.value}, now=utc_now())
        raise Forbidden(f"role {user.role.value} may not change categories")
    t = session.scalar(select(Transaction).join(Account, Transaction.account_id == Account.id).where(
        Account.business_id == user.business_id, Transaction.id == transaction_id))
    if t is None:
        audit.append(session, actor, "recategorize_not_found", base, now=utc_now())
        raise NotFound(f"transaction {transaction_id} not found")
    before = t.category.value if t.category else None
    t.category, t.category_source, t.needs_review = category, CategorySource.human, False
    rule = _rule_for(session, user.business_id, t, category)
    audit.append(session, actor, "transaction_recategorized",
                 base | {"from": before, "to": category.value, "rule_id": rule.id, "rule_kind": rule.kind.value},
                 now=utc_now())
    refresh_after_recategorize(session, user.business_id, today)
    return t
