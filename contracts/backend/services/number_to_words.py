from __future__ import annotations

UNITS_M = {
    0: "", 1: "один", 2: "два", 3: "три", 4: "четыре", 5: "пять",
    6: "шесть", 7: "семь", 8: "восемь", 9: "девять",
}
UNITS_F = {**UNITS_M, 1: "одна", 2: "две"}
TEENS = {
    10: "десять", 11: "одиннадцать", 12: "двенадцать", 13: "тринадцать",
    14: "четырнадцать", 15: "пятнадцать", 16: "шестнадцать", 17: "семнадцать",
    18: "восемнадцать", 19: "девятнадцать",
}
TENS = {
    2: "двадцать", 3: "тридцать", 4: "сорок", 5: "пятьдесят",
    6: "шестьдесят", 7: "семьдесят", 8: "восемьдесят", 9: "девяносто",
}
HUNDREDS = {
    1: "сто", 2: "двести", 3: "триста", 4: "четыреста", 5: "пятьсот",
    6: "шестьсот", 7: "семьсот", 8: "восемьсот", 9: "девятьсот",
}


def _plural(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n) % 100
    if 11 <= n <= 14:
        return forms[2]
    last = n % 10
    if last == 1:
        return forms[0]
    if 2 <= last <= 4:
        return forms[1]
    return forms[2]


def _triad_to_words(n: int, gender: str = "m") -> str:
    if not 0 <= n <= 999:
        raise ValueError("triad must be between 0 and 999")
    units = UNITS_F if gender == "f" else UNITS_M
    parts: list[str] = []
    h = n // 100
    if h:
        parts.append(HUNDREDS[h])
    rem = n % 100
    if 10 <= rem <= 19:
        parts.append(TEENS[rem])
    else:
        t = rem // 10
        u = rem % 10
        if t:
            parts.append(TENS[t])
        if u:
            parts.append(units[u])
    return " ".join(p for p in parts if p)


def int_to_words_ru(n: int) -> str:
    """Russian integer words for contract sums. Supports 0..999,999,999."""
    if n == 0:
        return "ноль"
    if n < 0 or n > 999_999_999:
        raise ValueError("Only values from 0 to 999,999,999 are supported")

    millions = n // 1_000_000
    thousands = (n // 1_000) % 1000
    rest = n % 1000
    parts: list[str] = []

    if millions:
        parts.append(_triad_to_words(millions, "m"))
        parts.append(_plural(millions, ("миллион", "миллиона", "миллионов")))
    if thousands:
        parts.append(_triad_to_words(thousands, "f"))
        parts.append(_plural(thousands, ("тысяча", "тысячи", "тысяч")))
    if rest:
        parts.append(_triad_to_words(rest, "m"))

    return " ".join(parts)


def rubles_to_words(n: int) -> str:
    return f"{int_to_words_ru(int(n))} рублей 00 копеек"
