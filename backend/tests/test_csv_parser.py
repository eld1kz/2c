"""CSV parser: both golden formats detected by header, exact integer cents, T11 upload limits."""

import csv
import io
from datetime import date

import pytest

from app.ingestion.csv_parser import MAX_BYTES, MAX_ROWS, CsvError, parse_cents, parse_csv
from seed.generate_golden import GOLDEN_DIR, Q2_FILE, Q3_FILE, TARGET_CASH_AT_DEMO_TODAY, build


def _golden(name: str) -> bytes:
    return (GOLDEN_DIR / name).read_bytes()


def _csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode()


def test_q2_signed_amount_format() -> None:
    rows = parse_csv("x.csv", _golden(Q2_FILE))
    assert len(rows) == 148
    assert rows[0].date == date(2026, 4, 1)
    assert rows[1].description == "ACH DEBIT MAPLEWOOD PROPERTY GRP RENT"
    assert rows[1].amount == -450_000


def test_q3_debit_credit_format() -> None:
    rows = parse_csv("x.csv", _golden(Q3_FILE))
    assert len(rows) == 158
    assert rows[0].date == date(2026, 7, 1) and rows[0].amount > 0  # credit
    assert rows[1].amount == -450_000  # debit shown unsigned in the file


@pytest.mark.parametrize("name", [Q2_FILE, Q3_FILE])
def test_running_balance_reproduced_exactly(name: str) -> None:
    rows = parse_csv(name, _golden(name))
    balance = rows[0].balance - rows[0].amount
    for row in rows:
        balance += row.amount
        assert balance == row.balance, f"line {row.line_no}"


def test_golden_totals_match_generator() -> None:
    rows = parse_csv("a.csv", _golden(Q2_FILE)) + parse_csv("b.csv", _golden(Q3_FILE))
    assert sum(r.amount for r in rows) == sum(r.amount for r in build()[0])
    assert rows[-1].balance == TARGET_CASH_AT_DEMO_TODAY


def test_detects_by_header_not_filename_or_column_order() -> None:
    text = _golden(Q3_FILE).decode().splitlines()
    reader = list(csv.reader(text))
    order = [4, 3, 1, 0, 2]  # shuffle columns
    shuffled = _csv([[r[i] for i in order] for r in reader])
    assert parse_csv("bank_checking_2026Q2.csv", shuffled) == parse_csv("x.csv", _golden(Q3_FILE))


@pytest.mark.parametrize("text, cents", [
    ("4500.00", 450_000), ("-4,500.00", -450_000), ("(12.34)", -1_234), ("$1,234.5", 123_450),
    ("0.07", 7), ("+3", 300), (" 69.00 ", 6_900),
])
def test_parse_cents_valid(text: str, cents: int) -> None:
    assert parse_cents(text) == cents


@pytest.mark.parametrize("text", ["1.234", "1e3", "NaN", "", "abc", "12.3.4", "--5", "1 000"])
def test_parse_cents_invalid(text: str) -> None:
    with pytest.raises(CsvError):
        parse_cents(text)


@pytest.mark.parametrize("rows, message", [
    ([["Date", "Amount"], ["2026-04-01", "1.00"]], "description"),
    ([["Date", "Description"], ["2026-04-01", "X"]], "amount"),
    ([["Date", "Description", "Amount", "Debit", "Credit"], ["2026-04-01", "X", "1.00", "", "1.00"]], "either"),
    ([["Date", "Description", "Debit", "Credit"], ["2026-04-01", "X", "1.00", "2.00"]], "exactly one"),
    ([["Date", "Description", "Debit", "Credit"], ["2026-04-01", "X", "", ""]], "exactly one"),
    ([["Date", "Description", "Amount"], ["13/04/2026", "X", "1.00"]], "date format"),
    ([["Date", "Description", "Amount"], ["2026-04-01", "X", "1.00"], ["04/02/2026", "Y", "1.00"]], "date format"),
    ([["Date", "Description", "Amount"], ["2026-04-01", "X", "12.345"]], "line 2"),
])
def test_rejects_bad_files(rows: list[list[str]], message: str) -> None:
    with pytest.raises(CsvError, match=message):
        parse_csv("x.csv", _csv(rows))


def test_bad_row_rejects_whole_file() -> None:
    rows = [["Date", "Description", "Amount"], ["2026-04-01", "OK", "1.00"], ["2026-04-02", "BAD", "x"]]
    with pytest.raises(CsvError, match="line 3"):
        parse_csv("x.csv", _csv(rows))


# --- T11: upload limits ------------------------------------------------------


def test_rejects_oversized_file() -> None:
    with pytest.raises(CsvError, match="exceeds"):
        parse_csv("x.csv", b"Date,Description,Amount\n" + b"a" * MAX_BYTES)


def test_rejects_binary_file() -> None:
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    with pytest.raises(CsvError, match="NUL"):
        parse_csv("x.csv", png)


def test_rejects_non_utf8() -> None:
    with pytest.raises(CsvError, match="UTF-8"):
        parse_csv("x.csv", "Date,Description,Amount\n2026-04-01,CAFÉ,1.00\n".encode("latin-1"))


@pytest.mark.parametrize("name", ["statement.xlsx", "statement.csv.exe", "statement"])
def test_rejects_wrong_extension(name: str) -> None:
    with pytest.raises(CsvError, match=".csv"):
        parse_csv(name, _golden(Q2_FILE))


def test_rejects_too_many_rows() -> None:
    rows = [["Date", "Description", "Amount"]] + [["2026-04-01", "X", "1.00"]] * (MAX_ROWS + 1)
    with pytest.raises(CsvError, match="rows"):
        parse_csv("x.csv", _csv(rows))


def test_rejects_unrecognised_header() -> None:
    with pytest.raises(CsvError, match="header"):
        parse_csv("x.csv", b"foo,bar\n1,2\n")
