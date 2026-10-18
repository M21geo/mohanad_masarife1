"""Money helpers.

Amounts are stored as integers in *minor units* so that sums never drift:
IQD has 0 decimals (1 unit = 1 dinar), USD has 2 decimals (1 unit = 1 cent).
Exchange rates are expressed as "IQD per 1 USD" (e.g. 1480).
"""
from decimal import Decimal, ROUND_HALF_UP

CURRENCIES = {"IQD": 0, "USD": 2}
SYMBOLS = {"IQD": "د.ع", "USD": "$"}


def _check(cur: str) -> None:
    if cur not in CURRENCIES:
        raise ValueError(f"unsupported currency: {cur}")


def to_minor(amount, cur: str) -> int:
    """User-facing amount (e.g. 12.5 USD) -> integer minor units (1250)."""
    _check(cur)
    q = Decimal(str(amount)) * (10 ** CURRENCIES[cur])
    return int(q.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def from_minor(minor: int, cur: str) -> Decimal:
    _check(cur)
    return Decimal(minor) / (10 ** CURRENCIES[cur])


def convert_minor(minor: int, from_cur: str, to_cur: str, rate) -> int:
    """Convert minor units between currencies using IQD-per-USD `rate`."""
    _check(from_cur)
    _check(to_cur)
    if from_cur == to_cur:
        return minor
    r = Decimal(str(rate))
    if r <= 0:
        raise ValueError("rate must be positive")
    value = from_minor(minor, from_cur)
    if from_cur == "IQD":  # IQD -> USD
        out = value / r
    else:  # USD -> IQD
        out = value * r
    return to_minor(out, to_cur)


def fmt(minor: int, cur: str, symbol: bool = True) -> str:
    """Format minor units for display: 1250000 IQD -> '1,250,000 د.ع'."""
    _check(cur)
    value = from_minor(minor, cur)
    digits = CURRENCIES[cur]
    text = f"{value:,.{digits}f}"
    if digits and text.endswith("." + "0" * digits):
        text = text[: -(digits + 1)]  # $150.00 -> $150
    if not symbol:
        return text
    return f"${text}" if cur == "USD" else f"{text} {SYMBOLS[cur]}"


# ------------------------------------------------------------ typed-number helpers
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬،", "0123456789.,,")


def format_input(text, decimals: bool = True) -> str:
    """Live thousands separators for text fields: '10000000' -> '10,000,000', '1234.5' -> '1,234.5'."""
    s = "".join(ch for ch in str(text or "").translate(_DIGITS) if ch.isdigit() or ch == ".")
    int_part, dot, frac = s.partition(".")
    has_dot = bool(dot) and decimals
    int_part = str(int(int_part)) if int_part else ("0" if has_dot else "")
    out = f"{int(int_part):,}" if int_part else ""
    if has_dot:
        out += "." + frac.replace(".", "")[:2]
    return out


def parse_input(text) -> float:
    """Typed amount (with separators / Arabic digits) -> float; 0.0 when empty or invalid."""
    try:
        return float(format_input(text).replace(",", "") or 0)
    except ValueError:
        return 0.0
