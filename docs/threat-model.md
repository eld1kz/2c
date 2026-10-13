# Threat model (living document → becomes security-assessment.md)

| # | Threat | Vector | Mitigation | Test | Status |
|---|---|---|---|---|---|
| T1 | Prompt injection via documents | Invoice notes / descriptions instruct agent to pay | Untrusted text wrapped as data; payee allowlist enforced in gate; no new bank details from documents | A1 | planned |
| T2 | Agent executes without consent | LLM calls EXECUTE tool | EXECUTE only creates `proposed` Action; agent has no approve tool; human approval via authenticated API | Phase 4 tier tests | planned |
| T3 | Excessive payment | Agent or user requests large transfer | `max_single_payment` limit → DENY | A2 | planned |
| T4 | Privilege escalation | Viewer/accountant approves restricted action | RBAC checks on every route + gate | A3 | planned |
| T5 | Duplicate execution | Retries / double clicks | Idempotency key, unique constraint | A4 | planned |
| T6 | Log tampering | DB edit to hide action | Hash-chained AuditEvent + verify endpoint; append-only | A5 | planned |
| T7 | Hallucinated numbers | LLM invents figures | All numbers from engine tools; citations required | Phase 4 smoke | planned |
| T8 | PII leakage to LLM | Account numbers/emails in prompts | `pii.py` masking before LLM calls | unit test | planned |
| T9 | Secret leakage | Keys in repo | `.env` gitignored; env-only config | CI grep check | planned |
| T10 | Abuse of chat endpoint | Spamming / cost | Rate limit per user | unit test | planned |
| T11 | Malicious upload | Huge / non-CSV file | Size + type limits, parser sandboxed from execution | unit test | planned |

## Known residual risks (be honest in the report)
- Demo auth (JWT, seeded users) is not production-grade identity.
- LLM categorization can still mislabel; mitigated by confidence threshold + human review, not eliminated.
- Forecast is heuristic (historical behavior); not a guarantee.
- Financing catalog is simulated, not real offers.
