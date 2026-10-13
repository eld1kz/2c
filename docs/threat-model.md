# Threat model (living document → becomes security-assessment.md)

| # | Threat | Vector | Mitigation | Test | Status |
|---|---|---|---|---|---|
| T1 | Prompt injection via documents | Invoice notes / descriptions instruct agent to pay | Untrusted text wrapped as data; `schedule_payment` takes only counterparty id + payable invoice id (no payee name / bank details), pays stored details only; gate DENIES non-allowlisted payee, invoice not an open payable of that counterparty, or amount > invoice outstanding | A1 (incl. injection mapped onto QuickShip: $4,650 vs QS-2291 $465 → DENY); `test_llm_classifier.py` | in progress — A1 planted in golden data (QS-2291 notes); gate rules specified (SPEC §8), implemented in Phase 3. Phase 1 categorizer: system prompt is a fixed constant; descriptions reach the LLM only as normalized `[A-Z0-9 ]` text inside a JSON array, reply is schema-constrained and re-validated, rules always win over the LLM; ingestion never creates counterparties from description text. Phase 2 engine: `engine/snapshot.py` never loads invoice `notes`, so forecast/what-if cannot be steered by them (`test_invoice_notes_never_affect_the_forecast`) |
| T2 | Agent executes without consent | LLM calls EXECUTE tool | EXECUTE only creates `proposed` Action; agent has no approve tool; human approval via authenticated API | Phase 4 tier tests | planned |
| T3 | Excessive payment | Agent or user requests large transfer | `max_single_payment` limit → DENY | A2 | planned |
| T4 | Privilege escalation | Viewer/accountant approves restricted action | RBAC checks on every route + gate | A3 | planned |
| T5 | Duplicate execution | Retries / double clicks | Idempotency key, unique constraint | A4 | planned |
| T6 | Log tampering | DB edit to hide action | Hash-chained AuditEvent + verify endpoint; append-only | A5 | in progress — ORM blocks AuditEvent update/delete via unit-of-work and bulk ORM `update()`/`delete()` through a Session; raw SQL (e.g. `text()` or a direct DB connection) can still modify rows until Phase 3's DB trigger; hash chain + verify in Phase 3 |
| T7 | Hallucinated numbers | LLM invents figures | All numbers from engine tools; citations required | Phase 4 smoke; `test_forecast.py` | in progress — every ForecastLine carries source_ids that resolve to real records (account/invoice/recurring_series/transaction); integer cents only; agent citations in Phase 4 |
| T8 | PII leakage to LLM | Account numbers/emails in prompts | `pii.py` masking before LLM calls | unit test | in progress — categorizer sends only normalized descriptions (card numbers, terminal IDs, phones, refs stripped) + direction, no amounts or DB ids (`test_llm_classifier.py`); agent `pii.py` in Phase 4 |
| T9 | Secret leakage | Keys in repo | `.env` gitignored; env-only config | CI grep check | in progress — `.env` gitignored, only `.env.example` committed |
| T10 | Abuse of chat endpoint | Spamming / cost | Rate limit per user | unit test | planned |
| T11 | Malicious upload | Huge / non-CSV file | Size + type limits, parser sandboxed from execution | `test_csv_parser.py` | in progress — parser enforces ≤2 MB, `.csv`, UTF-8, no NUL bytes, ≤20k rows, recognised header, all-or-nothing; stdlib `csv` only, nothing evaluated. HTTP upload route (with RBAC + audit) in Phase 3 |

## Known residual risks (be honest in the report)
- Demo auth (JWT, seeded users) is not production-grade identity.
- All seeded demo users share one known password (`seed/load.py`); demo data only.
- LLM categorization can still mislabel; mitigated by confidence threshold + human review, not eliminated.
- Forecast is heuristic (historical behavior); not a guarantee.
- Financing catalog is simulated, not real offers.
