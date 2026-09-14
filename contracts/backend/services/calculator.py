from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
TARIFFS_PATH = ROOT / "config" / "tariffs.json"
MONTH_ORDINALS = [
    "первый", "второй", "третий", "четвертый", "пятый", "шестой",
    "седьмой", "восьмой", "девятый", "десятый", "одиннадцатый", "двенадцатый",
]


def load_tariffs() -> dict[str, Any]:
    return json.loads(TARIFFS_PATH.read_text(encoding="utf-8"))


def distribute(total: int, weights: list[int]) -> list[int]:
    """Distribute integer rubles by weights. Last row compensates rounding."""
    total = int(round(total))
    if total < 0:
        raise ValueError("Сумма не может быть отрицательной")
    if not weights or sum(weights) <= 0:
        raise ValueError("Некорректные веса распределения")
    weight_sum = sum(weights)
    values = [round(total * w / weight_sum) for w in weights]
    diff = total - sum(values)
    values[-1] += diff
    return values


def calculate_services(months: int, total_price: int, reputation_total: int | None = None, include_reputation: bool = True) -> dict[str, Any]:
    tariffs = load_tariffs()
    plan = tariffs["plans"].get(str(months))
    if not plan:
        raise ValueError("Поддерживаются только сроки 3, 6 или 12 месяцев")

    total_price = int(total_price)
    include_reputation = bool(include_reputation)
    if not include_reputation:
        reputation_total = 0
    else:
        reputation_total = int(plan["default_reputation_total"] if reputation_total in (None, "") else reputation_total)

    if total_price <= 0:
        raise ValueError("Итоговая сумма должна быть больше нуля")
    if reputation_total < 0:
        raise ValueError("Сумма репутации не может быть отрицательной")
    if reputation_total > total_price:
        raise ValueError("Репутация не может быть больше общей суммы договора")

    maps_total = total_price - reputation_total
    maps_months = distribute(maps_total, list(map(int, plan["maps_weights"])))
    reputation_months = distribute(reputation_total, list(map(int, plan["reputation_weights"]))) if include_reputation and reputation_total > 0 else []

    rows = []
    rows.append({"type": "section", "name": "Услуги Исполнителя по управлению профилем Заказчика в сервисах Карт: Яндекс.Карты", "amount": maps_total})
    for i, amount in enumerate(maps_months):
        rows.append({"type": "item", "name": f"За {MONTH_ORDINALS[i]} месяц", "amount": amount})
    if include_reputation and reputation_total > 0:
        rows.append({"type": "section", "name": "Услуги Исполнителя по Репутации в сети", "amount": reputation_total})
        for i, amount in enumerate(reputation_months):
            rows.append({"type": "item", "name": f"За {MONTH_ORDINALS[i]} месяц", "amount": amount})
    rows.append({"type": "total", "name": "Всего", "amount": total_price})

    return {
        "months": months,
        "months_text": plan["months_text"],
        "total_price": total_price,
        "maps_total": maps_total,
        "reputation_total": reputation_total,
        "maps_months": maps_months,
        "reputation_months": reputation_months,
        "include_reputation": include_reputation and reputation_total > 0,
        "rows": rows,
        "warnings": []
    }


def format_money(value: int | float) -> str:
    n = int(round(value))
    return f"{n:,}".replace(",", " ") + ",00"
