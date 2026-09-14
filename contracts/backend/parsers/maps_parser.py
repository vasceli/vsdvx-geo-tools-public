from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from backend.services.formatting import clean_text


MOJIBAKE_RE = re.compile(r"(?:[ÐÑ][\x80-\xbf]|�|Ã|Â)")
GENERIC_YANDEX_TITLES = {"яндекс карты", "яндекс.карты", "yandex maps", "яндекс", "карты"}


def extract_yandex_profile_id(url: str) -> str:
    patterns = [
        r"/profile/(\d+)",
        r"/org/[^/]+/(\d+)",
        r"oid=(\d+)",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return ""


def _safe_json_string_decode(value: str) -> str:
    """Decode JSON/URL escaped fragments without turning normal Cyrillic into mojibake."""
    value = value or ""
    decoded = value
    try:
        decoded = json.loads(f'"{value}"')
    except Exception:
        decoded = unquote(value)
        if "\\u" in decoded or "\\x" in decoded:
            try:
                decoded = decoded.encode("utf-8", "ignore").decode("unicode_escape", "ignore")
            except Exception:
                pass
    decoded = clean_text(decoded)
    if MOJIBAKE_RE.search(decoded):
        return ""
    return decoded


def _is_generic_title(value: str) -> bool:
    v = clean_text(value).lower().strip(" —-|")
    if v in GENERIC_YANDEX_TITLES:
        return True
    if "яндекс" in v and "кар" in v and len(v) < 30:
        return True
    return False


def _sanitize_name(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"\s*[—|-]\s*Яндекс.*$", "", value, flags=re.I)
    value = re.sub(r"\s*на карте.*$", "", value, flags=re.I)
    if _is_generic_title(value) or MOJIBAKE_RE.search(value):
        return ""
    return value


def _sanitize_address(value: str) -> str:
    value = clean_text(value)
    # Generic descriptions are worse than blank because they overwrite manual fields.
    if not value or MOJIBAKE_RE.search(value):
        return ""
    if re.search(r"Яндекс\s*Карты|карты\s+покажут|маршрут|панорамы", value, re.I):
        return ""
    return value


def _jsonld_candidates(soup: BeautifulSoup) -> dict[str, str]:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "{}")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            name = _sanitize_name(item.get("name", ""))
            address = item.get("address", "")
            if isinstance(address, dict):
                # Keep normal address ordering when schema fields are present.
                preferred = ["postalCode", "addressRegion", "addressLocality", "streetAddress"]
                parts = [str(address[k]) for k in preferred if address.get(k)]
                if not parts:
                    parts = [str(v) for v in address.values() if v]
                address = _sanitize_address(", ".join(parts))
            else:
                address = _sanitize_address(str(address))
            if name or address:
                return {"org_name": name, "org_address": address}
    return {}


def parse_yandex_maps_url(url: str, timeout: int = 10) -> dict[str, Any]:
    """Best-effort parser. Direct Yandex HTML parsing is fragile; UI must keep manual fallback."""
    url = clean_text(url)
    profile_id = extract_yandex_profile_id(url)
    result: dict[str, Any] = {
        "maps_link": url,
        "profile_id": profile_id,
        "org_name": "",
        "org_address": "",
        "source": "manual_fallback_required",
        "needs_manual_check": True,
        "warnings": []
    }
    if not url:
        result["warnings"].append("Ссылка пустая")
        return result

    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            },
            allow_redirects=True,
        )
        response.raise_for_status()
    except Exception as exc:
        result["warnings"].append(f"Не удалось открыть страницу карт: {exc}")
        return result

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    ld = _jsonld_candidates(soup)
    if ld:
        result.update(ld)
        result["source"] = "json_ld"

    if not result["org_name"]:
        meta_title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "title"})
        raw_title = meta_title.get("content", "") if meta_title else (soup.title.string if soup.title else "")
        title = _sanitize_name(raw_title)
        if title:
            result["org_name"] = title
            result["source"] = "meta_title"

    if not result["org_address"]:
        meta_desc = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "description"})
        desc = clean_text(meta_desc.get("content", "") if meta_desc else "")
        m = re.search(r"Адрес\s*[:—-]\s*([^.;]+(?:[,][^.;]+)*)", desc, re.I)
        if m:
            result["org_address"] = _sanitize_address(m.group(1))

    # Fallback regexes over embedded state. Only use safe decoded strings.
    if not result["org_name"]:
        for pattern in [r'"name"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', r'"title"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"']:
            m = re.search(pattern, html)
            if m:
                candidate = _sanitize_name(_safe_json_string_decode(m.group(1)))
                if candidate:
                    result["org_name"] = candidate
                    result["source"] = "embedded_json"
                    break

    if not result["org_address"]:
        for pattern in [r'"address"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', r'"formattedAddress"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"']:
            m = re.search(pattern, html)
            if m:
                candidate = _sanitize_address(_safe_json_string_decode(m.group(1)))
                if candidate:
                    result["org_address"] = candidate
                    result["source"] = "embedded_json"
                    break

    if not result["org_name"] or not result["org_address"]:
        result["warnings"].append("Автопарсинг карт неполный. Проверьте и дозаполните вручную.")
    return result
