import hashlib
import json
import os
import secrets
import requests

from datetime import timedelta

from django.utils import timezone

from .models import Employee, TelegramLinkRequest


LINK_TTL_MINUTES = 15

_SESSION = None


def telegram_session():
    global _SESSION

    if _SESSION is not None:
        return _SESSION

    session = requests.Session()

    # Не наследуем случайные HTTP(S)_PROXY из окружения.
    session.trust_env = False

    proxy_url = os.environ.get(
        "TELEGRAM_PROXY_URL",
        "",
    ).strip()

    if proxy_url:
        session.proxies.update({
            "http": proxy_url,
            "https": proxy_url,
        })

    _SESSION = session
    return session


def token_hash(token):
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def create_link_request(
    *,
    employee,
    telegram_user_id,
    telegram_chat_id,
    telegram_username="",
):
    raw_token = secrets.token_urlsafe(32)

    request = TelegramLinkRequest.objects.create(
        employee=employee,
        token_hash=token_hash(raw_token),
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id,
        telegram_username=telegram_username or "",
        expires_at=(
            timezone.now()
            + timedelta(minutes=LINK_TTL_MINUTES)
        ),
    )

    return request, raw_token


def find_link_request(raw_token):
    try:
        return (
            TelegramLinkRequest.objects
            .select_related("employee")
            .get(token_hash=token_hash(raw_token))
        )
    except TelegramLinkRequest.DoesNotExist:
        return None


def telegram_api(method, payload=None, timeout=10):
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/{method}"
    )

    try:
        response = telegram_session().post(
            url,
            data=payload or {},
            timeout=(5, timeout),
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Telegram transport error: {exc}"
        ) from exc

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Telegram returned invalid JSON "
            f"(HTTP {response.status_code})"
        ) from exc

    if (
        response.status_code >= 400
        or not result.get("ok")
    ):
        raise RuntimeError(
            f"Telegram API HTTP "
            f"{response.status_code}: {result}"
        )

    return result.get("result")


def send_message(
    chat_id,
    text,
    *,
    reply_markup=None,
):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }

    if reply_markup:
        payload["reply_markup"] = json.dumps(
            reply_markup,
            ensure_ascii=False,
        )

    return telegram_api(
        "sendMessage",
        payload,
    )


def answer_callback(callback_query_id, text=""):
    return telegram_api(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_query_id,
            "text": text,
        },
    )


def employee_keyboard():
    employees = (
        Employee.objects
        .filter(is_active=True)
        .exclude(username__in=["backlog_import", "admin"])
        .order_by("display_name", "username")
    )

    rows = []

    for employee in employees:
        rows.append([
            {
                "text": (
                    employee.display_name
                    or employee.username
                ),
                "callback_data": (
                    f"link_employee:{employee.pk}"
                ),
            }
        ])

    return {
        "inline_keyboard": rows,
    }


def confirm_link_keyboard(url):
    return {
        "inline_keyboard": [
            [
                {
                    "text": "Подтвердить в Backlog",
                    "url": url,
                }
            ]
        ],
    }
