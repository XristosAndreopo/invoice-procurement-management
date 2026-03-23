"""
Shared monetary and Greek amount-to-words helpers for reports.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def to_decimal(value: Any) -> Decimal:
    """
    Safely convert a numeric-like value to Decimal.
    """
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0.00")


def money_plain(value: Any) -> str:
    """
    Format decimal-like value using Greek-style separators without currency.

    Example
    -------
    1700.5 -> "1.700,50"
    """
    amount = to_decimal(value).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def money(value: Any) -> str:
    """
    Format decimal-like value with currency symbol.
    """
    return f"{money_plain(value)} €"


def percent(value: Any) -> str:
    """
    Format decimal-like percentage value with Greek separators but no % sign.
    """
    amount = to_decimal(value).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def int_to_greek_words_genitive(n: int) -> str:
    """
    Convert a non-negative integer to Greek words in genitive case.

    Suitable for document phrases such as:
    - συνολικής αξίας ...
    - ποσού ...

    Supported range:
    0 <= n <= 999_999_999
    """
    if n < 0:
        raise ValueError("Negative values are not supported.")
    if n == 0:
        return "μηδενός"

    units = {
        0: "",
        1: "ενός",
        2: "δύο",
        3: "τριών",
        4: "τεσσάρων",
        5: "πέντε",
        6: "έξι",
        7: "επτά",
        8: "οκτώ",
        9: "εννέα",
    }

    teens = {
        10: "δέκα",
        11: "έντεκα",
        12: "δώδεκα",
        13: "δεκατριών",
        14: "δεκατεσσάρων",
        15: "δεκαπέντε",
        16: "δεκαέξι",
        17: "δεκαεπτά",
        18: "δεκαοκτώ",
        19: "δεκαεννέα",
    }

    tens = {
        2: "είκοσι",
        3: "τριάντα",
        4: "σαράντα",
        5: "πενήντα",
        6: "εξήντα",
        7: "εβδομήντα",
        8: "ογδόντα",
        9: "ενενήντα",
    }

    hundreds = {
        1: "εκατόν",
        2: "διακοσίων",
        3: "τριακοσίων",
        4: "τετρακοσίων",
        5: "πεντακοσίων",
        6: "εξακοσίων",
        7: "επτακοσίων",
        8: "οκτακοσίων",
        9: "εννιακοσίων",
    }

    def two_digits(num: int) -> str:
        if num < 10:
            return units[num]
        if 10 <= num <= 19:
            return teens[num]

        t = num // 10
        u = num % 10
        if u == 0:
            return tens[t]
        return f"{tens[t]} {units[u]}".strip()

    def three_digits(num: int) -> str:
        if num < 100:
            return two_digits(num)

        h = num // 100
        rem = num % 100

        if rem == 0:
            if h == 1:
                return "εκατό"
            return hundreds[h]

        return f"{hundreds[h]} {two_digits(rem)}".strip()

    parts: list[str] = []

    millions = n // 1_000_000
    remainder = n % 1_000_000

    thousands = remainder // 1_000
    below_thousand = remainder % 1_000

    if millions:
        if millions == 1:
            parts.append("ενός εκατομμυρίου")
        else:
            parts.append(f"{three_digits(millions)} εκατομμυρίων")

    if thousands:
        if thousands == 1:
            parts.append("χιλίων")
        else:
            parts.append(f"{three_digits(thousands)} χιλιάδων")

    if below_thousand:
        parts.append(three_digits(below_thousand))

    return " ".join(p for p in parts if p).strip()


def money_words_el(value: Any) -> str:
    """
    Convert a numeric amount to Greek words in genitive case.

    Examples
    --------
    1755.00 -> χιλίων επτακοσίων πενήντα πέντε ευρώ
    1755.20 -> χιλίων επτακοσίων πενήντα πέντε ευρώ και είκοσι λεπτών
    """
    amount = to_decimal(value).quantize(Decimal("0.01"))

    euros = int(amount)
    cents = int((amount - Decimal(euros)) * 100)

    euro_words = int_to_greek_words_genitive(euros)

    if cents == 0:
        return f"{euro_words} ευρώ"

    cents_words = int_to_greek_words_genitive(cents)
    return f"{euro_words} ευρώ και {cents_words} λεπτών"


__all__ = [
    "to_decimal",
    "money_plain",
    "money",
    "percent",
    "int_to_greek_words_genitive",
    "money_words_el",
]