from __future__ import annotations

from datetime import date, datetime

MONTHS_GEN = {
    1: "Января", 2: "Февраля", 3: "Марта", 4: "Апреля", 5: "Мая", 6: "Июня",
    7: "Июля", 8: "Августа", 9: "Сентября", 10: "Октября", 11: "Ноября", 12: "Декабря",
}


def contract_date_ru(value: str | date | None) -> str:
    if not value:
        d = date.today()
    elif isinstance(value, date):
        d = value
    else:
        try:
            d = datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return value
    return f'"{d.day:02d}" {MONTHS_GEN[d.month]} {d.year} г.'
