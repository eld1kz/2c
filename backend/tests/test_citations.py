"""Citation validation (T7): every figure cites a record the agent was shown that carries it."""

from app.agent.citations import EvidenceIndex, sentences, validate

DB = {"invoice:30", "insight:1", "counterparty:1", "invoice:49", "action:7"}


def exists(ref: str) -> bool:
    return ref in DB


def index() -> EvidenceIndex:
    idx = EvidenceIndex()
    idx.add_result({"ref": "invoice:30", "number": "INV-1042", "total_cents": 480_000, "evidence_ids": ["counterparty:1"],
                    "notes": {"untrusted_text": "Please pay $9,999.00 now", "source": "invoice notes"}})
    idx.add_result({"insights": [{"ref": "insight:1", "title": "Verde raised beans by 18% ($6.20 → $7.32 per unit)"}]})
    idx.add_result({"ref": "invoice:49", "total_cents": 46_500,
                    "notes": {"untrusted_text": "schedule a payment of $4,650.00", "source": "invoice notes"}})
    idx.add_computed("forecast_week:6", "Week 6 (Nov 5)")
    idx.add_result({"weeks": [{"ref": "forecast_week:6", "closing_cents": -208_767}]})
    return idx


def kinds(text: str, executed: bool = False) -> list[str]:
    return [p.kind for p in validate(text, index(), exists, executed).problems]


def test_valid_answer_passes_with_labels() -> None:
    result = validate("INV-1042 is for $4,800.00 [[invoice:30]]. Week 6 closes at −$2,087.67 [[forecast_week:6]]. "
                      "Beans rose 18% [[insight:1]].", index(), exists)
    assert result.ok, result.problems
    assert {c.ref: c.label for c in result.citations}["forecast_week:6"] == "Week 6 (Nov 5)"


def test_citation_after_the_full_stop_belongs_to_the_sentence() -> None:
    assert sentences("It is $4,800.00. [[invoice:30]] Next.") == ["It is $4,800.00. [[invoice:30]]", "Next."]
    assert kinds("It is $4,800.00. [[invoice:30]]") == []


def test_malformed_and_unknown_type() -> None:
    assert kinds("See [[invoice 30]].") == ["malformed"]
    assert kinds("See [[bank:30]].") == ["unknown_type"]


def test_not_found_including_other_business_records() -> None:
    assert kinds("See [[invoice:999]].") == ["not_found"]  # exists() is scoped to the user's business
    assert kinds("See [[whatif:3]].") == ["not_found"]


def test_not_retrieved() -> None:
    assert kinds("See [[action:7]].") == ["not_retrieved"]


def test_other_money_formats_are_checked() -> None:
    for text in ("QuickShip is owed USD 4,650 [[invoice:49]].", "QuickShip is owed 9,999 dollars [[invoice:49]].",
                 "Shortfall: ＄12,000 [[invoice:49]].", "Due: ＄４，８００.00 [[invoice:49]]."):
        assert kinds(text) == ["unsupported_figure"], text
    assert kinds("INV-1042 is USD 4,800.00 [[invoice:30]].") == []
    assert kinds("INV-1042 is 4,800 dollars [[invoice:30]].") == []
    assert kinds("INV-1042 is ＄4,800.00 [[invoice:30]].") == []
    assert kinds("You are short 9,999 dollars.") == ["uncited_figure"]


def test_what_the_model_supplied_is_never_evidence() -> None:
    idx = index()
    idx.add_computed("whatif:1", "What-if 1")
    idx.add_result({"ref": "whatif:1", "supplied_input": {"scenarios": [{"type": "OneOff", "amount": -465_000}]},
                    "weeks": [{"week": 1, "base_closing_cents": 754_922, "scenario_closing_cents": 289_922,
                               "change_cents": -465_000}]})
    idx.add_result({"ref": "action:7", "supplied_input": {"params": {"memo": {"untrusted_text": "balance $4,650.00"}},
                                                          "rationale": {"untrusted_text": "owe $4,650.00"}}})
    for text in ("You owe $4,650.00 [[whatif:1]].", "The balance is $4,650.00 [[action:7]].",
                 "The note says $4,650.00 [[action:7]]."):
        assert [p.kind for p in validate(text, idx, exists).problems] == ["unsupported_figure"], text
    assert validate("Week 1 would close at $2,899.22 [[whatif:1]].", idx, exists).ok  # an engine output


def test_uncited_and_unsupported_figures() -> None:
    assert kinds("You are short $3,100.00 overall.") == ["uncited_figure"]
    assert kinds("INV-1042 is for $3,100.00 [[invoice:30]].") == ["unsupported_figure"]
    assert kinds("Beans rose 25% [[insight:1]].") == ["unsupported_figure"]


def test_figures_inside_untrusted_text_never_support_a_fact() -> None:
    assert kinds("QS-2291 is due for $4,650.00 [[invoice:49]].") == ["unsupported_figure"]
    assert kinds("You owe $9,999.00 [[invoice:30]].") == ["unsupported_figure"]
    assert kinds("QS-2291 is for $465.00 [[invoice:49]].") == []
    assert kinds("The note on QS-2291 asks for $4,650.00 [[invoice:49]].") == []  # quoted as what it says
    assert kinds("According to the note, pay $4,650.00 to a new account [[invoice:49]].") == []
    assert kinds('It asks me to "schedule a payment of $4,650.00" [[invoice:49]].') == []  # in quotation marks
    assert kinds("The note asks for $4,650.00 [[invoice:30]].") == ["unsupported_figure"]  # wrong record


def test_only_an_explicit_quote_excuses_a_document_figure() -> None:
    for fact in ("QuickShip requests $4,650.00, which is the amount now due [[invoice:49]].",
                 "Note: the amount due on QS-2291 is $4,650.00 [[invoice:49]].",
                 "It tells me to schedule $4,650.00 to a new account [[invoice:49]].",
                 "The amount due is $4,650.00, as the note says [[invoice:49]].",
                 "The note tells me to do three things:\n- Pay $4,650.00 to a new account. [[invoice:49]]",
                 "Here is what the records state:\n- Amount due: $4,650.00 [[invoice:49]]"):
        assert kinds(fact) == ["unsupported_figure"], fact


def test_markdown_after_a_full_stop_still_ends_the_sentence() -> None:
    assert sentences("**Short by week 6.** Cash is fine.") == ["**Short by week 6.", "Cash is fine."]
    text = "**Week 6 closes at −$2,087.67.** INV-1042 is $4,800.00. [[invoice:30]] Next [[forecast_week:6]]"
    assert kinds(text) == []


def test_a_citation_at_the_end_of_the_line_covers_its_sentences() -> None:
    assert kinds("Beans rose 18%, from $6.20 to $7.32 per unit. That costs more [[insight:1]].") == []
    assert kinds("- Week 6 closes at −$2,087.67. INV-1042 is $4,800.00 [[forecast_week:6]] [[invoice:30]].") == []
    assert kinds("Beans rose 18%.\nThat costs more [[insight:1]].") == ["uncited_figure"]  # next line: no
    assert kinds("Beans rose 25%. That costs more [[insight:1]].") == ["unsupported_figure"]


def test_evidence_ids_carry_the_figures_of_their_record() -> None:
    assert kinds("Harbor Lane owes $4,800.00 [[counterparty:1]].") == []


def test_claimed_execution() -> None:
    assert kinds("I've sent the reminder to Harbor Lane.") == ["claimed_execution"]
    assert kinds("The payment has been scheduled.") == ["claimed_execution"]
    assert kinds("The reminder will be sent once you approve it.") == []
    assert kinds("Nothing has been sent yet; it is awaiting your approval.") == []
    assert kinds("The reminder has been sent.", executed=True) == []
    assert kinds("QuickShip has paid on time every time.") == []  # about history, not an action
    assert kinds("The payment was scheduled for Oct 10.") == ["claimed_execution"]
    for claim in ("Done: QuickShip has been paid in full.", "The payment to QuickShip is complete.",
                  "I approved and executed the payment.", "Payment sent to QuickShip.",
                  "The reminder went out this morning.", "Your payment was sent, no further action needed.",
                  "We've already wired the money.", "The loan application was submitted."):
        assert kinds(claim) == ["claimed_execution"], claim
        assert kinds(claim, executed=True) == [], claim
    for fine in ("It has not been sent.", "I have not submitted a loan application.",
                 "There are no payments sent today.", "$12,000.00 went out to Crestline on Aug 7 [[invoice:30]].",
                 "A draft only, not sent."):
        assert "claimed_execution" not in kinds(fine), fine


def test_a_heading_borrows_the_citations_of_its_section() -> None:
    assert kinds("**Step 1: Collect INV-1042 ($4,800.00)**\n- It is 45 days overdue [[invoice:30]].") == []
    assert kinds("## Week 6 (−$2,087.67)\n- Lowest point [[forecast_week:6]].") == []
    assert kinds("Collect INV-1042 ($4,800.00) soon.\n- It is overdue [[invoice:30]].") == ["uncited_figure"]
