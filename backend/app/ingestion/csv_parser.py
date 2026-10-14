"""Bank-statement CSV parser (SPEC §6.1).

The format is detected from the header row, never the filename. Money is parsed from the
string straight to integer cents; no float or Decimal is involved at any step.
Upload limits (threat model T11) are enforced before anything is decoded.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 20_000
MAX_ABS_CENTS = 10**12  # $10bn per row: far above any SME row, far below BIGINT overflow
DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y"]  # DD/MM is ambiguous for a USD bank, so not accepted

HEADER_ALIASES = {
    "date": {"date", "posting date", "transaction date", "posted date", "value date"},
    "description": {"description", "transaction details", "details", "memo", "narrative"},
    "amount": {"amount", "transaction amount"},
    "debit": {"debit", "withdrawal", "withdrawals", "money out"},
    "credit": {"credit", "deposit", "deposits", "money in"},
    "balance": {"balance", "running balance"},
}

_MONEY = re.compile(r"^(\d+)(?:\.(\d{1,2}))?$")


class CsvError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedRow:
    line_no: int
    date: date
    amount: int  # signed cents: inflow > 0
    description: str
    balance: int | None  # validation only; not stored


def parse_cents(text: str) -> int:
    s = text.strip().replace("$", "").replace(",", "")
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()
    if s and s[0] in "+-":
        negative, s = negative ^ (s[0] == "-"), s[1:]
    m = _MONEY.match(s)
    if not m:
        raise CsvError(f"not a money amount: {text!r}")
    cents = int(m.group(1)) * 100 + int((m.group(2) or "").ljust(2, "0"))
    if cents > MAX_ABS_CENTS:
        raise CsvError(f"amount out of range: {text!r}")
    return -cents if negative else cents


def _check_limits(filename: str, data: bytes) -> str:
    if not filename.lower().endswith(".csv"):
        raise CsvError("only .csv files are accepted")
    if len(data) > MAX_BYTES:
        raise CsvError(f"file exceeds {MAX_BYTES} bytes")
    if b"\x00" in data:
        raise CsvError("file contains NUL bytes; not a text CSV")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise CsvError("file is not valid UTF-8") from e


def _columns(header: list[str]) -> dict[str, int]:
    cols: dict[str, int] = {}
    for i, name in enumerate(header):
        key = " ".join(name.strip().lower().replace("_", " ").split())
        for field, aliases in HEADER_ALIASES.items():
            if key in aliases:
                if field in cols:
                    raise CsvError(f"duplicate {field} column")
                cols[field] = i
    if "date" not in cols or "description" not in cols:
        raise CsvError("unrecognised header: need date and description columns")
    has_amount = "amount" in cols
    has_split = "debit" in cols and "credit" in cols
    if has_amount == has_split:
        raise CsvError("need either an amount column or both debit and credit columns")
    return cols


def _parses(value: str, fmt: str) -> bool:
    try:
        datetime.strptime(value, fmt)
        return True
    except ValueError:
        return False


def _date_format(values: list[tuple[int, str]]) -> str:
    """One format per file: the first that parses every row."""
    for fmt in DATE_FORMATS:
        if all(_parses(v, fmt) for _, v in values):
            return fmt
    bad = next((n for n, v in values if not any(_parses(v, f) for f in DATE_FORMATS)), values[0][0])
    raise CsvError(f"line {bad}: unsupported or inconsistent date format")


def _amount(cells: list[str], cols: dict[str, int]) -> int:
    if "amount" in cols:
        return parse_cents(cells[cols["amount"]])
    debit, credit = cells[cols["debit"]].strip(), cells[cols["credit"]].strip()
    if bool(debit) == bool(credit):
        raise CsvError("exactly one of debit/credit must be filled")
    return parse_cents(credit) if credit else -abs(parse_cents(debit))


def parse_csv(filename: str, data: bytes) -> list[ParsedRow]:
    """Parse a whole statement or raise CsvError listing every bad line (all-or-nothing)."""
    reader = csv.reader(io.StringIO(_check_limits(filename, data)))
    header = next(reader, None)
    if header is None:
        raise CsvError("empty file")
    cols = _columns(header)

    records = [(n, cells) for n, cells in enumerate(reader, start=2) if any(c.strip() for c in cells)]
    if len(records) > MAX_ROWS:
        raise CsvError(f"more than {MAX_ROWS} rows")
    if not records:
        raise CsvError("no data rows")
    width = max(cols.values()) + 1
    short = [n for n, cells in records if len(cells) < width]
    if short:
        raise CsvError(f"lines with missing columns: {short[:10]}")

    fmt = _date_format([(n, cells[cols["date"]].strip()) for n, cells in records])
    rows: list[ParsedRow] = []
    errors: list[str] = []
    for n, cells in records:
        try:
            balance = parse_cents(cells[cols["balance"]]) if "balance" in cols and cells[cols["balance"]].strip() else None
            rows.append(ParsedRow(
                line_no=n,
                date=datetime.strptime(cells[cols["date"]].strip(), fmt).date(),
                amount=_amount(cells, cols),
                description=cells[cols["description"]].strip(),
                balance=balance,
            ))
        except CsvError as e:
            errors.append(f"line {n}: {e}")
    if errors:
        raise CsvError("; ".join(errors[:10]))
    return rows
