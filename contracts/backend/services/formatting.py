from __future__ import annotations

import re
from html import escape


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u00a0", " ").replace("\u200b", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def html_escape(value: object) -> str:
    return escape(clean_text(value))


def initials_from_name(full_name: str) -> str:
    parts = [p for p in re.split(r"\s+", clean_text(full_name)) if p]
    if not parts:
        return ""
    if len(parts) >= 3:
        surname, name, patronymic = parts[0], parts[1], parts[2]
        return f"{name[0]}. {patronymic[0]}. {surname}"
    if len(parts) == 2:
        return f"{parts[1][0]}. {parts[0]}"
    return parts[0]
